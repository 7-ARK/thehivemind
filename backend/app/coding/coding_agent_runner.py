from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from app.coding.coding_policy import classify_task, is_protected_path
from app.coding.context_builder import CodingContextBuilder
from app.coding.patch_applier import PatchApplier
from app.coding.patch_parser import PARSER_ROUTES, PatchParseError, parse_proposed_patch_with_route
from app.coding.schemas import CodingContext, ProposedPatch, RealCodingAgentResult, RepairLoopStatus
from app.coding.validation import run_validation_commands, validation_commands_for_patch
from app.core.config import Settings, get_settings
from app.core.models import RunEvent
from app.core.model_registry import get_model_metadata
from app.core.cost_estimator import estimate_cost_usd, estimate_tokens
from app.projects.schemas import ProjectFileWriteResult
from app.providers.provider_router import generate_with_provider
from app.workspace.schemas import CommandResult


class RealCodingAgentRunner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.context_builder = CodingContextBuilder(self.settings)
        self.applier = PatchApplier(self.settings)

    async def run(
        self,
        *,
        project_id: str,
        run_id: str,
        command: str,
        mode: str,
        allow_safe_commands: bool,
        memory_packet: Any | None = None,
        model_id: str | None = None,
        fallback_model_id: str | None = None,
        allow_live_coding_model_call: bool = False,
        dry_run: bool = False,
        max_files: int | None = None,
        max_repair_attempts: int | None = None,
        max_cost_usd: float | None = None,
    ) -> tuple[RealCodingAgentResult, list[ProjectFileWriteResult], list[Any], RunEvent]:
        selected_model = model_id or self.settings.real_coding_agent_model
        fallback_model = fallback_model_id or self.settings.real_coding_agent_fallback_model
        effective_max_files = max_files or max(self.settings.real_coding_max_input_files, self.settings.real_coding_max_output_files)
        effective_max_repair_attempts = min(1, max(0, max_repair_attempts if max_repair_attempts is not None else self.settings.real_coding_max_repair_attempts))
        task_type = classify_task(command)
        context = self.context_builder.build(
            project_id=project_id,
            run_id=run_id,
            command=command,
            task_type=task_type,
            max_files=effective_max_files,
            memory_packet=memory_packet if self.settings.real_coding_use_memory else None,
        )
        prompt = self.context_builder.render_prompt(context)
        live_call_made = False
        mock_simulated = mode == "mock"
        provider = "mock" if mode == "mock" else "openrouter"
        provider_metadata: dict[str, Any] = {}
        provider_response_diagnostic: dict[str, Any] | None = None
        fallback_model_used = False
        parse_error: str | None = None
        parser_route: str | None = None
        requested_max_output_tokens = None
        response_format_requested: str | None = None
        provider_response_finish_reason: str | None = None
        actual_output_tokens: int | None = None
        reasoning_tokens: int | None = None
        content_source: str | None = None
        notes = [
            "GPT-5.5 was not used because coding worker tasks use OpenRouter coding models and GPT-5.5 remains CEO-gated.",
        ]
        repair_loop = RepairLoopStatus(
            repair_enabled=effective_max_repair_attempts > 0,
            max_attempts=effective_max_repair_attempts,
        )

        if mode == "live":
            self._assert_live_coding_allowed(allow_live_coding_model_call)
            response_text, selected_model, live_call_made, provider_metadata, fallback_model_used = await self._call_openrouter(
                prompt=prompt,
                model_id=selected_model,
                fallback_model_id=fallback_model,
                run_id=run_id,
                project_id=project_id,
            )
            requested_max_output_tokens = provider_metadata.get("requested_max_tokens") or self.settings.real_coding_max_output_tokens
            response_format_requested = _response_format_name(provider_metadata.get("requested_response_format"))
            provider_response_finish_reason = provider_metadata.get("finish_reason")
            actual_output_tokens = provider_metadata.get("actual_output_tokens")
            reasoning_tokens = provider_metadata.get("reasoning_tokens")
            content_source = provider_metadata.get("content_source")
        else:
            response_text = json.dumps(self._mock_patch(context), indent=2)
            requested_max_output_tokens = self.settings.real_coding_max_output_tokens
            response_format_requested = "none"
            actual_output_tokens = estimate_tokens(response_text)
            content_source = "mock"
        initial_input_tokens = estimate_tokens(prompt)
        initial_output_tokens = actual_output_tokens if actual_output_tokens is not None else estimate_tokens(response_text)
        repair_loop.initial_patch_estimated_cost_usd = estimate_cost_usd(selected_model, initial_input_tokens, initial_output_tokens)

        try:
            parsed = parse_proposed_patch_with_route(response_text)
            patch = parsed.patch
            parser_route = parsed.parser_route
        except PatchParseError as exc:
            parse_error = str(exc)
            parser_route = exc.parser_route
            if live_call_made:
                provider_response_diagnostic = _provider_response_diagnostic(
                    provider=provider,
                    model=selected_model,
                    metadata=provider_metadata,
                    text=response_text,
                    final_rejection_reason=parse_error,
                    parser_route=parser_route,
                    actual_output_tokens=actual_output_tokens,
                    reasoning_tokens=reasoning_tokens,
                    content_source=content_source,
                )
            patch = ProposedPatch(
                summary="Rejected: coding model output was not a valid file patch.",
                task_type=task_type,
                files_to_change=[],
                files_read=[item.path for item in context.selected_files],
                risk_notes=[parse_error],
                memory_used=context.memory_used[:3],
            )
            validation = self.applier.validate(patch, task_type=task_type, file_scope=context.allowed_user_file_scope, max_output_files=effective_max_files, project_id=project_id)
            validation.accepted = False
            validation.violations.append(parse_error)
            applied_entries: list[ProjectFileWriteResult] = []
            applied_files = []
            validation_results = []
        else:
            validation = self.applier.validate(patch, task_type=task_type, file_scope=context.allowed_user_file_scope, max_output_files=effective_max_files, project_id=project_id)
            if live_call_made and not validation.accepted:
                provider_response_diagnostic = _provider_response_diagnostic(
                    provider=provider,
                    model=selected_model,
                    metadata=provider_metadata,
                    text=response_text,
                    final_rejection_reason="; ".join(validation.violations) or "Patch validation rejected the proposed change.",
                    parser_route=parser_route,
                    actual_output_tokens=actual_output_tokens,
                    reasoning_tokens=reasoning_tokens,
                    content_source=content_source,
                )
            if validation.accepted:
                effective_dry_run = dry_run or self.settings.real_coding_dry_run
                snapshot = None if effective_dry_run else self._snapshot_files(project_id, patch)
                applied_entries, applied_files = self.applier.apply(
                    project_id=project_id,
                    run_id=run_id,
                    patch=patch,
                    dry_run=effective_dry_run,
                )
                commands = validation_commands_for_patch(patch, task_type)
                validation_results = [] if effective_dry_run else run_validation_commands(
                    project_id=project_id,
                    run_id=run_id,
                    commands=commands,
                    allow_safe_commands=allow_safe_commands,
                    settings=self.settings,
                )
                repair_loop, applied_entries, applied_files, validation_results = await self._maybe_repair(
                    project_id=project_id,
                    run_id=run_id,
                    command=command,
                    mode=mode,
                    context=context,
                    first_patch=patch,
                    first_validation=validation,
                    first_validation_results=validation_results,
                    first_snapshot=snapshot,
                    task_type=task_type,
                    selected_model=selected_model,
                    fallback_model=fallback_model,
                    allow_live_coding_model_call=allow_live_coding_model_call,
                    allow_safe_commands=allow_safe_commands,
                    dry_run=effective_dry_run,
                    effective_max_files=effective_max_files,
                    effective_max_repair_attempts=effective_max_repair_attempts,
                    initial_estimated_cost_usd=repair_loop.initial_patch_estimated_cost_usd,
                    max_cost_usd=max_cost_usd,
                    applied_files=applied_files,
                    applied_entries=applied_entries,
                    validation_results=validation_results,
                )
                dry_run = effective_dry_run
            else:
                applied_entries = []
                applied_files = []
                validation_results = []

        patch_applied = bool(applied_entries) and validation.accepted and not dry_run
        no_change_reason = None
        if parse_error:
            no_change_reason = "No user-facing changes were applied because the coding provider response was invalid or empty."
        if repair_loop.rollback_attempted:
            no_change_reason = "Repair validation failed; original pre-run file contents were restored."
        elif validation.accepted and not patch_applied and not (dry_run or self.settings.real_coding_dry_run):
            no_change_reason = "Requested content already matches the current file, or no safe improvement was necessary."
        memory_items = patch.memory_used or context.memory_used[:3]
        memory_exclusions = [
            str(item.get("summary"))
            for item in memory_items
            if item.get("type") == "memory_filter_note" and item.get("summary")
        ]
        visible_memory_items = [item for item in memory_items if item.get("type") != "memory_filter_note"]
        result = RealCodingAgentResult(
            enabled=self.settings.enable_real_coding_agent,
            used=True,
            actual_provider=provider,
            selected_model=selected_model,
            fallback_model=fallback_model,
            fallback_model_used=fallback_model_used,
            live_call_made=live_call_made,
            mock_simulated=mock_simulated,
            dry_run=dry_run or self.settings.real_coding_dry_run,
            hardcoded_fallback_used=False,
            patch_applied=patch_applied,
            no_change_reason=no_change_reason,
            parse_error=parse_error,
            parser_route=parser_route,
            parser_route_attempted=PARSER_ROUTES,
            provider_response_diagnostic=provider_response_diagnostic,
            requested_max_output_tokens=requested_max_output_tokens,
            response_format_requested=response_format_requested,
            provider_response_finish_reason=provider_response_finish_reason,
            actual_output_tokens=actual_output_tokens,
            reasoning_tokens=reasoning_tokens,
            content_source=content_source,
            repair_attempts=repair_loop.attempts_made,
            repair_loop=repair_loop,
            task_type=task_type,
            allowed_user_file_scope=context.allowed_user_file_scope,
            files_inspected=[item.path for item in context.file_map if not item.protected],
            files_selected=[item.path for item in context.selected_files],
            files_changed=[entry.path for entry in applied_entries] if patch_applied and not repair_loop.rollback_attempted else [],
            rejected_files=[change.path for change in patch.files_to_change] if not validation.accepted else [],
            validation=validation,
            proposed_patch=patch,
            applied_files=applied_files,
            validation_commands=[item.model_dump() for item in validation_results],
            memory_used=visible_memory_items[:4],
            memory_exclusions=memory_exclusions,
            search_context_used=any(item.get("type") == "research_source_summary" for item in context.memory_used),
            notes=notes,
        )
        event = self._event_from_result(
            run_id=run_id,
            command=command,
            result=result,
            prompt=prompt,
            output=response_text,
        )
        return result, applied_entries, validation_results, event

    async def _maybe_repair(
        self,
        *,
        project_id: str,
        run_id: str,
        command: str,
        mode: str,
        context: CodingContext,
        first_patch: ProposedPatch,
        first_validation: Any,
        first_validation_results: list[CommandResult],
        first_snapshot: dict[str, Any] | None,
        task_type: str,
        selected_model: str,
        fallback_model: str | None,
        allow_live_coding_model_call: bool,
        allow_safe_commands: bool,
        dry_run: bool,
        effective_max_files: int,
        effective_max_repair_attempts: int,
        initial_estimated_cost_usd: float,
        max_cost_usd: float | None,
        applied_files: list[Any],
        applied_entries: list[ProjectFileWriteResult],
        validation_results: list[CommandResult],
    ) -> tuple[RepairLoopStatus, list[ProjectFileWriteResult], list[Any], list[CommandResult]]:
        status = RepairLoopStatus(
            repair_enabled=effective_max_repair_attempts > 0,
            max_attempts=effective_max_repair_attempts,
            initial_patch_estimated_cost_usd=initial_estimated_cost_usd,
        )
        status.artifacts["repair_policy"] = {
            "repair_enabled": status.repair_enabled,
            "max_attempts": status.max_attempts,
            "eligible_only_after": "accepted patch, applied patch, approved safe validation command executed, validation command failed",
            "dry_run": dry_run,
        }
        failed_command = _first_failed_allowed_command(first_validation_results)
        if not status.repair_enabled:
            status.not_attempted_reason = "Repair disabled by request/config."
            status.final_result = "not_attempted_disabled"
            return status, applied_entries, applied_files, validation_results
        if dry_run:
            status.not_attempted_reason = "Dry-run mode never applies patches, repairs, or rollback."
            status.final_result = "not_attempted_dry_run"
            return status, applied_entries, applied_files, validation_results
        if not first_validation.accepted:
            status.not_attempted_reason = "Patch schema/scope/protected-path validation failed before apply."
            status.final_result = "not_attempted_patch_rejected"
            return status, applied_entries, applied_files, validation_results
        if not applied_entries:
            status.not_attempted_reason = "No initial file changes were applied."
            status.final_result = "not_attempted_no_initial_apply"
            return status, applied_entries, applied_files, validation_results
        if failed_command is None:
            status.not_attempted_reason = "No approved safe validation command failed."
            status.final_result = "not_attempted_no_failed_validation"
            return status, applied_entries, applied_files, validation_results

        repair_prompt = self._repair_prompt(
            command=command,
            context=context,
            first_patch=first_patch,
            failed_command=failed_command,
        )
        repair_estimated_cost = estimate_cost_usd(
            selected_model,
            estimate_tokens(repair_prompt),
            self.settings.real_coding_max_output_tokens,
        )
        status.repair_patch_estimated_cost_usd = repair_estimated_cost
        if mode == "live" and max_cost_usd is not None and initial_estimated_cost_usd + repair_estimated_cost > max_cost_usd:
            status.cost_cap_prevented_repair = True
            status.not_attempted_reason = "Repair provider call skipped because estimated repair cost would exceed max_cost_usd."
            status.final_result = "not_attempted_cost_cap"
            return status, applied_entries, applied_files, validation_results

        status.attempts_made = 1
        status.reason_repair_started = "Initial approved safe validation command failed after patch application."
        status.initial_validation_failed = True
        status.initial_validation_command = failed_command.command
        status.initial_validation_exit_code = failed_command.exit_code
        status.artifacts["repair_attempt_1_context"] = self._repair_context_artifact(
            command=command,
            context=context,
            first_patch=first_patch,
            failed_command=failed_command,
        )

        repair_response = await self._repair_response_text(
            mode=mode,
            prompt=repair_prompt,
            context=context,
            first_patch=first_patch,
            failed_command=failed_command,
            selected_model=selected_model,
            fallback_model=fallback_model,
            run_id=run_id,
            project_id=project_id,
            allow_live_coding_model_call=allow_live_coding_model_call,
        )
        try:
            repair_patch = parse_proposed_patch_with_route(repair_response).patch
            repair_validation = self.applier.validate(
                repair_patch,
                task_type=task_type,  # type: ignore[arg-type]
                file_scope=context.allowed_user_file_scope,
                max_output_files=effective_max_files,
                project_id=project_id,
            )
        except PatchParseError as exc:
            repair_patch = None
            repair_validation = first_validation.model_copy(update={"accepted": False, "violations": [str(exc)]})

        status.repair_patch_accepted = repair_validation.accepted
        status.artifacts["repair_attempt_1_result"] = {
            "attempt_number": 1,
            "repair_enabled": True,
            "repair_patch_accepted": repair_validation.accepted,
            "violations": repair_validation.violations,
            "warnings": repair_validation.warnings,
            "repair_patch": repair_patch.model_dump() if repair_patch else None,
        }
        if not repair_patch or not repair_validation.accepted:
            rollback = self._restore_snapshot(first_snapshot)
            status.rollback_attempted = True
            status.rollback_succeeded = rollback["rollback_succeeded"]
            status.rollback_failed_files = rollback["rollback_failed_files"]
            status.final_result = "failed_safely_original_files_restored" if rollback["rollback_succeeded"] else "failed_rollback_error"
            status.artifacts["rollback_result"] = rollback
            return status, [], applied_files, validation_results

        repair_entries, repair_applied_files = self.applier.apply(
            project_id=project_id,
            run_id=run_id,
            patch=repair_patch,
            dry_run=False,
            agent_name="Real Coding Agent Repair",
        )
        status.repair_patch_applied = bool(repair_entries)
        repair_validation_results = run_validation_commands(
            project_id=project_id,
            run_id=run_id,
            commands=[failed_command.command],
            allow_safe_commands=allow_safe_commands,
            settings=self.settings,
        )
        validation_results = [*validation_results, *repair_validation_results]
        repair_command = repair_validation_results[0] if repair_validation_results else None
        repair_passed = bool(repair_command and repair_command.allowed and repair_command.exit_code == 0)
        status.repair_validation_passed = repair_passed
        status.artifacts["repair_validation_result"] = {
            "attempt_number": 1,
            "safe_command": failed_command.command,
            "exit_code": repair_command.exit_code if repair_command else None,
            "repair_validation_passed": repair_passed,
        }
        if repair_passed:
            status.final_result = "repaired_successfully"
            return status, repair_entries, repair_applied_files, validation_results

        rollback = self._restore_snapshot(first_snapshot)
        status.rollback_attempted = True
        status.rollback_succeeded = rollback["rollback_succeeded"]
        status.rollback_failed_files = rollback["rollback_failed_files"]
        status.final_result = "failed_safely_original_files_restored" if rollback["rollback_succeeded"] else "failed_rollback_error"
        status.artifacts["rollback_result"] = rollback
        return status, [], [*applied_files, *repair_applied_files], validation_results

    def _snapshot_files(self, project_id: str, patch: ProposedPatch) -> dict[str, Any]:
        root = self.applier.manager.get_project_root(project_id)
        manifest_path = root / "manifest.json"
        files = {}
        for change in patch.files_to_change:
            relative = change.path.replace("\\", "/")
            protected, reason = is_protected_path(relative)
            if protected:
                raise HTTPException(status_code=400, detail=f"Cannot snapshot protected path {relative}: {reason}")
            target = self.applier.manager.resolve(project_id, relative)
            files[relative] = {
                "existed": target.exists(),
                "content": target.read_text(encoding="utf-8") if target.exists() else None,
            }
        return {
            "project_id": project_id,
            "files": files,
            "manifest_content": manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None,
        }

    def _restore_snapshot(self, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if not snapshot:
            return {"rollback_attempted": True, "rollback_succeeded": False, "rollback_failed_files": ["snapshot_missing"]}
        project_id = snapshot["project_id"]
        root = self.applier.manager.get_project_root(project_id)
        failed = []
        for relative, payload in snapshot["files"].items():
            try:
                target = self.applier.manager.resolve(project_id, relative)
                if payload["existed"]:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(payload["content"] or "", encoding="utf-8")
                elif target.exists():
                    target.unlink()
            except Exception:
                failed.append(relative)
        try:
            manifest_content = snapshot.get("manifest_content")
            if manifest_content is not None:
                (root / "manifest.json").write_text(manifest_content, encoding="utf-8")
        except Exception:
            failed.append("manifest.json")
        return {
            "rollback_attempted": True,
            "rollback_succeeded": not failed,
            "rollback_failed_files": failed,
        }

    async def _repair_response_text(
        self,
        *,
        mode: str,
        prompt: str,
        context: CodingContext,
        first_patch: ProposedPatch,
        failed_command: CommandResult,
        selected_model: str,
        fallback_model: str | None,
        run_id: str,
        project_id: str,
        allow_live_coding_model_call: bool,
    ) -> str:
        if mode == "mock":
            return json.dumps(self._mock_repair_patch(context, first_patch, failed_command), indent=2)
        self._assert_live_coding_allowed(allow_live_coding_model_call)
        response_text, _model, _live, _metadata, _fallback = await self._call_openrouter(
            prompt=prompt,
            model_id=selected_model,
            fallback_model_id=fallback_model or self.settings.real_coding_agent_fallback_model,
            run_id=run_id,
            project_id=project_id,
            task_suffix="repair_attempt_1",
        )
        return response_text

    def _repair_prompt(self, *, command: str, context: CodingContext, first_patch: ProposedPatch, failed_command: CommandResult) -> str:
        return (
            "You are TheHiveMind Real Coding Agent repair loop v1. Return strict JSON only. "
            "Create one replacement patch inside the same approved file scope. Do not add files outside scope.\n\n"
            + json.dumps(
                self._repair_context_artifact(command=command, context=context, first_patch=first_patch, failed_command=failed_command),
                indent=2,
            )
        )

    def _repair_context_artifact(self, *, command: str, context: CodingContext, first_patch: ProposedPatch, failed_command: CommandResult) -> dict[str, Any]:
        changed_paths = [change.path.replace("\\", "/") for change in first_patch.files_to_change]
        current_files = {}
        for path in changed_paths[: self.settings.real_coding_max_output_files]:
            try:
                content = self.applier.manager.read_project_file(context.project_id, path)
            except Exception:
                content = ""
            current_files[path] = _redact_preview(content[:1200])
        return {
            "attempt_number": 1,
            "original_user_request": command,
            "allowed_user_file_scope": context.allowed_user_file_scope.model_dump(),
            "current_failed_file_content": current_files,
            "safe_validation_command": failed_command.command,
            "exit_code": failed_command.exit_code,
            "stdout_summary": _redact_preview((failed_command.stdout or "")[-1200:]),
            "stderr_summary": _redact_preview((failed_command.stderr or "")[-1200:]),
            "first_patch_summary": first_patch.summary,
            "instruction": "Return only a valid structured patch JSON object. Stay inside allowed_user_file_scope.",
        }

    def _mock_repair_patch(self, context: CodingContext, first_patch: ProposedPatch, failed_command: CommandResult) -> dict[str, Any]:
        changes = []
        for change in first_patch.files_to_change:
            path = change.path.replace("\\", "/")
            if path.endswith(".py"):
                content = 'print("Real Coding Agent repair validation passed")\n'
            else:
                content = (change.new_content or "").rstrip() + "\n<!-- Repair attempt: validation-safe content retained. -->\n"
            changes.append(
                {
                    "path": path,
                    "reason": "Repair the failed safe validation command without expanding file scope.",
                    "change_type": "modify",
                    "new_content": content,
                }
            )
        return {
            "summary": "Mock repair patch generated after safe validation failure.",
            "task_type": context.task_type,
            "files_to_change": changes,
            "files_read": [item.path for item in context.selected_files],
            "validation_commands": [{"cmd": failed_command.command, "reason": "Rerun the same approved validation command after repair."}],
            "risk_notes": ["One bounded repair attempt only.", "Same prompt-level file scope retained."],
            "memory_used": context.memory_used[:4],
        }

    def _assert_live_coding_allowed(self, allow_live_coding_model_call: bool) -> None:
        if not self.settings.enable_real_coding_agent:
            raise HTTPException(status_code=403, detail="Real Coding Agent is disabled.")
        if not self.settings.allow_live_calls:
            raise HTTPException(status_code=403, detail="Live provider calls are disabled. Set ALLOW_LIVE_CALLS=true.")
        if not self.settings.allow_real_coding_agent:
            raise HTTPException(status_code=403, detail="Live Real Coding Agent calls are disabled. Set ALLOW_REAL_CODING_AGENT=true.")
        if not allow_live_coding_model_call:
            raise HTTPException(status_code=403, detail="This run did not allow a live coding model call.")
        if not self.settings.openrouter_api_key:
            raise HTTPException(status_code=400, detail="OpenRouter API key is not configured.")

    async def _call_openrouter(self, *, prompt: str, model_id: str, fallback_model_id: str, run_id: str, project_id: str, task_suffix: str = "real_coding_agent") -> tuple[str, str, bool, dict[str, Any], bool]:
        messages = [
            {"role": "system", "content": "You are a careful coding agent. Return JSON only: no markdown fences, no prose, no commentary."},
            {"role": "user", "content": prompt},
        ]
        max_output_tokens = self.settings.real_coding_max_output_tokens
        response_format = {"type": "json_object"}
        try:
            response, _usage_id = await generate_with_provider(
                provider="openrouter",
                model=model_id,
                mode="live",
                messages=messages,
                max_output_tokens=max_output_tokens,
                temperature=0.1,
                run_id=run_id,
                task_id=f"{run_id}:{task_suffix}",
                agent_name="Real Coding Agent" if task_suffix == "real_coding_agent" else "Real Coding Agent Repair",
                agent_role="Project file editing" if task_suffix == "real_coding_agent" else "Bounded coding repair",
                project_id=project_id,
                request_type="real_coding_agent",
                response_format=response_format,
                settings=self.settings,
            )
            return response.text, model_id, True, _response_metadata_with_tokens(response.raw_metadata, response.output_tokens), False
        except HTTPException:
            response, _usage_id = await generate_with_provider(
                provider="openrouter",
                model=fallback_model_id,
                mode="live",
                messages=messages,
                max_output_tokens=max_output_tokens,
                temperature=0.1,
                run_id=run_id,
                task_id=f"{run_id}:{task_suffix}:fallback",
                agent_name="Real Coding Agent" if task_suffix == "real_coding_agent" else "Real Coding Agent Repair",
                agent_role="Project file editing" if task_suffix == "real_coding_agent" else "Bounded coding repair",
                project_id=project_id,
                request_type="real_coding_agent",
                response_format=response_format,
                settings=self.settings,
            )
            return response.text, fallback_model_id, True, _response_metadata_with_tokens(response.raw_metadata, response.output_tokens), True

    def _mock_patch(self, context: CodingContext) -> dict[str, Any]:
        changes = []
        for item in context.selected_files[: self.settings.real_coding_max_output_files]:
            new_content = _mock_updated_content(item.path, item.content, context.command, context.memory_used)
            if new_content != item.content:
                changes.append(
                    {
                        "path": item.path,
                        "reason": item.reason,
                        "change_type": "modify",
                        "new_content": new_content,
                    }
                )
        faq_allowed, _scope_reason = (
            True,
            "",
        )
        if context.allowed_user_file_scope.allowed_user_files:
            faq_allowed = "website/data/faqs.json" in context.allowed_user_file_scope.allowed_user_files
        if context.task_type == "website_copy_update" and faq_allowed and not any(change["path"] == "website/data/faqs.json" for change in changes):
            changes.append(
                {
                    "path": "website/data/faqs.json",
                    "reason": "Homepage copy task benefits from editable FAQ/content data; sample order data is intentionally not touched.",
                    "change_type": "create",
                    "new_content": json.dumps(
                        [
                            {
                                "question": "Was this homepage copy updated by the Real Coding Agent?",
                                "answer": "Yes. The agent inspected project files, used relevant memory when available, and avoided order/sample data for this copy-only update.",
                            }
                        ],
                        indent=2,
                    )
                    + "\n",
                }
            )
        return {
            "summary": "Mock Real Coding Agent generated structured file edits from inspected project files.",
            "task_type": context.task_type,
            "files_to_change": changes,
            "files_read": [item.path for item in context.selected_files],
            "validation_commands": [{"cmd": cmd, "reason": "Safe validation option selected from file changes."} for cmd in context.validation_options],
            "risk_notes": ["No package install required.", "No deploy required.", "No secrets or .env files touched."],
            "memory_used": context.memory_used[:4],
        }

    def _event_from_result(self, *, run_id: str, command: str, result: RealCodingAgentResult, prompt: str, output: str) -> RunEvent:
        input_tokens = estimate_tokens(prompt)
        output_tokens = estimate_tokens(output)
        return RunEvent(
            timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
            run_id=run_id,
            agent_name="Real Coding Agent",
            agent_role="Project file editing",
            status="completed" if result.validation.accepted else "blocked",
            action_summary="Applied structured coding patch" if result.patch_applied else ("Prepared dry-run patch" if result.dry_run else "Rejected invalid coding patch" if result.parse_error else "Validated structured coding patch"),
            input_summary=command,
            output_summary=f"{result.actual_provider} / {result.selected_model}; parser: {result.parser_route or 'n/a'}; files selected: {', '.join(result.files_selected[:6])}; files changed: {', '.join(result.files_changed[:6]) or 'none'}"
            + (f"; parse error: {result.parse_error}" if result.parse_error else ""),
            model_used=result.selected_model,
            provider=result.actual_provider,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_tokens=input_tokens + output_tokens,
            estimated_cost_usd=estimate_cost_usd(result.selected_model, input_tokens, output_tokens),
            estimated_cost=estimate_cost_usd(result.selected_model, input_tokens, output_tokens),
        )


def _provider_response_diagnostic(
    *,
    provider: str,
    model: str,
    metadata: dict[str, Any],
    text: str,
    final_rejection_reason: str,
    parser_route: str | None,
    actual_output_tokens: int | None,
    reasoning_tokens: int | None,
    content_source: str | None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "http_status": metadata.get("http_status"),
        "finish_reason": metadata.get("finish_reason"),
        "requested_max_output_tokens": metadata.get("requested_max_tokens"),
        "actual_output_tokens": actual_output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "response_format_requested": _response_format_name(metadata.get("requested_response_format")),
        "content_length": len(text or ""),
        "content_source": content_source or metadata.get("content_source") or "unknown",
        "parser_route_attempted": PARSER_ROUTES,
        "parser_route": parser_route,
        "final_rejection_reason": final_rejection_reason,
        "response_shape": metadata.get("response_shape") or {},
        "safe_content_preview_start": _redacted_preview_start(text),
        "safe_content_preview_end": _redacted_preview_end(text),
    }


def _response_metadata_with_tokens(metadata: dict[str, Any], output_tokens: int) -> dict[str, Any]:
    enriched = dict(metadata)
    enriched.setdefault("actual_output_tokens", output_tokens)
    return enriched


def _first_failed_allowed_command(results: list[CommandResult]) -> CommandResult | None:
    for result in results:
        if result.allowed and result.exit_code != 0:
            return result
    return None


def _response_format_name(value: Any) -> str:
    if isinstance(value, dict) and value.get("type") == "json_object":
        return "json_object"
    return "none" if not value else str(value)


def _redacted_preview_start(text: str, limit: int = 240) -> str:
    preview = (text or "")[:limit]
    return _redact_preview(preview)


def _redacted_preview_end(text: str, limit: int = 240) -> str:
    preview = (text or "")[-limit:] if text else ""
    return _redact_preview(preview)


def _redact_preview(preview: str) -> str:
    lowered = preview.lower()
    secret_markers = ("sk-", "api_key", "apikey", "authorization", "bearer ", "private_key", "openrouter_api_key")
    if any(marker in lowered for marker in secret_markers):
        return "[redacted]"
    return preview


def _mock_updated_content(path: str, content: str, command: str, memory_used: list[dict[str, Any]]) -> str:
    memory_note = _memory_note(memory_used)
    lowered_path = path.lower()
    if lowered_path.endswith(".html"):
        explicit = _apply_explicit_html_replacements(content, command)
        if explicit != content:
            return explicit
        if "Real Coding Agent memory note:" in content:
            return content
        marker = "</section>"
        note = f"\n        <p><strong>Real Coding Agent memory note:</strong> {memory_note}</p>"
        if marker in content:
            return content.replace(marker, f"{note}\n      {marker}", 1)
        return content + f"\n<!-- Real Coding Agent memory note: {memory_note} -->\n"
    if lowered_path.endswith(".json"):
        try:
            payload = json.loads(content)
            if isinstance(payload, list):
                payload.append({"question": "Was this updated by the Real Coding Agent?", "answer": "Yes. The update was generated from inspected files and validated before apply."})
                return json.dumps(payload, indent=2) + "\n"
        except Exception:
            pass
    if lowered_path.endswith(".md"):
        if "Real Coding Agent update" in content:
            return content
        return content.rstrip() + f"\n\n## Real Coding Agent update\n\n- {command[:220]}\n- Memory/context note: {memory_note}\n"
    return content


def _apply_explicit_html_replacements(content: str, command: str) -> str:
    headline = _extract_exact_value(command, "headline")
    subheadline = _extract_exact_value(command, "subheadline")
    if not headline and not subheadline:
        return content
    updated = content
    if headline:
        updated, headline_count = re.subn(r"<h1([^>]*)>.*?</h1>", f"<h1\\1>{headline}</h1>", updated, count=1, flags=re.IGNORECASE | re.DOTALL)
        if headline_count == 0:
            updated = f"<h1>{headline}</h1>\n{updated}"
    if subheadline:
        updated, sub_count = re.subn(r"(<h1[^>]*>.*?</h1>\\s*)<p([^>]*)>.*?</p>", f"\\1<p\\2>{subheadline}</p>", updated, count=1, flags=re.IGNORECASE | re.DOTALL)
        if sub_count == 0:
            updated, sub_count = re.subn(r"<p([^>]*)>.*?</p>", f"<p\\1>{subheadline}</p>", updated, count=1, flags=re.IGNORECASE | re.DOTALL)
        if sub_count == 0:
            updated = updated.replace("</h1>", f"</h1>\n<p>{subheadline}</p>", 1) if "</h1>" in updated.lower() else f"<p>{subheadline}</p>\n{updated}"
    return updated


def _extract_exact_value(command: str, label: str) -> str | None:
    pattern = rf"{label}\s+with\s+exactly:\s*[\"“”']?(.+?)[\"“”']?(?:\n\s*\n|$)"
    match = re.search(pattern, command, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip().strip("\"“”'")
    return " ".join(value.split())


def _memory_note(memory_used: list[dict[str, Any]]) -> str:
    if not memory_used:
        return "No prior memory was used; current command and inspected files guided this edit."
    first = memory_used[0]
    summary = str(first.get("summary") or first.get("title") or "prior memory")
    return summary[:220]
