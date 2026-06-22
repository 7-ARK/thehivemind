from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from app.coding.coding_policy import classify_task
from app.coding.context_builder import CodingContextBuilder
from app.coding.patch_applier import PatchApplier
from app.coding.patch_parser import PARSER_ROUTES, PatchParseError, parse_proposed_patch_with_route
from app.coding.schemas import CodingContext, ProposedPatch, RealCodingAgentResult
from app.coding.validation import run_validation_commands, validation_commands_for_patch
from app.core.config import Settings, get_settings
from app.core.models import RunEvent
from app.core.model_registry import get_model_metadata
from app.core.cost_estimator import estimate_cost_usd, estimate_tokens
from app.projects.schemas import ProjectFileWriteResult
from app.providers.provider_router import generate_with_provider


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
    ) -> tuple[RealCodingAgentResult, list[ProjectFileWriteResult], list[Any], RunEvent]:
        selected_model = model_id or self.settings.real_coding_agent_model
        fallback_model = fallback_model_id or self.settings.real_coding_agent_fallback_model
        effective_max_files = max_files or max(self.settings.real_coding_max_input_files, self.settings.real_coding_max_output_files)
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
                dry_run = effective_dry_run
            else:
                applied_entries = []
                applied_files = []
                validation_results = []

        patch_applied = bool(applied_entries) and validation.accepted and not dry_run
        no_change_reason = None
        if parse_error:
            no_change_reason = "No user-facing changes were applied because the coding provider response was invalid or empty."
        if validation.accepted and not patch_applied and not (dry_run or self.settings.real_coding_dry_run):
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
            repair_attempts=0,
            task_type=task_type,
            allowed_user_file_scope=context.allowed_user_file_scope,
            files_inspected=[item.path for item in context.file_map if not item.protected],
            files_selected=[item.path for item in context.selected_files],
            files_changed=[entry.path for entry in applied_entries] if patch_applied else [],
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

    async def _call_openrouter(self, *, prompt: str, model_id: str, fallback_model_id: str, run_id: str, project_id: str) -> tuple[str, str, bool, dict[str, Any], bool]:
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
                task_id=f"{run_id}:real_coding_agent",
                agent_name="Real Coding Agent",
                agent_role="Project file editing",
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
                task_id=f"{run_id}:real_coding_agent:fallback",
                agent_name="Real Coding Agent",
                agent_role="Project file editing",
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
