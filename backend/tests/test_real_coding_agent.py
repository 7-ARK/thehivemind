from app.coding.coding_policy import classify_task, prompt_file_scope
from app.coding.context_builder import CodingContextBuilder
from app.coding.patch_applier import PatchApplier
from app.coding.project_inspector import ProjectInspector, select_relevant_files
from app.coding.schemas import CodingFileChange, ProposedPatch, RealCodingAgentResult, PatchValidationResult
from app.core.config import get_settings
from app.memory.context_packet import build_context_packet
from app.memory.memory_store import MemoryStore
from app.model_registry.selector_service import DynamicModelSelector
from app.model_registry.schemas import ModelSelectionRequest
from app.orchestration.execution_engine import ExecutionEngine
from app.projects.project_workspace import ProjectWorkspaceManager


def test_real_coding_agent_config_and_model_selection(client):
    settings = get_settings()
    assert settings.enable_real_coding_agent is True
    assert settings.allow_real_coding_agent is False
    assert settings.real_coding_agent_model == "moonshotai/kimi-k2.7-code"
    assert settings.real_coding_agent_fallback_model == "qwen/qwen3-coder"

    selection = DynamicModelSelector().select(
        ModelSelectionRequest(
            command="Improve homepage copy without GPT-5.5.",
            agent_id="real_coding_agent",
            agent_role="Real Coding Agent",
            agent_task="Edit project files.",
            mode="mock",
            run_type="website_update",
            required_capabilities=["coding", "tools", "json"],
            preferred_tags=["coding", "website", "json"],
            max_cost_usd=0.05,
        )
    )
    assert selection.selected_model_id == "moonshotai/kimi-k2.7-code"
    assert selection.provider == "openrouter"
    assert selection.fallback_model_id == "qwen/qwen3-coder"
    assert not selection.selected_model_id.startswith("gpt-5.5")


def test_project_inspection_excludes_secrets_and_marks_metadata(client):
    manager = ProjectWorkspaceManager()
    project_id = "inspect-test"
    manager.write_project_file(project_id, "website/templates/index.html", "<h1>Hello</h1>\n", "Test", "run-1", "homepage")
    root = manager.get_project_root(project_id)
    (root / ".env").write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
    (root / "service_account.json").write_text('{"private_key":"secret"}\n', encoding="utf-8")

    file_map = ProjectInspector().file_map(project_id)
    env_entry = next(item for item in file_map if item.path == ".env")
    service_entry = next(item for item in file_map if item.path == "service_account.json")
    state_entry = next(item for item in file_map if item.path == "project_state.md")
    assert env_entry.protected is True
    assert service_entry.protected is True
    assert state_entry.system_metadata is True


def test_relevant_file_selector_homepage_and_status(client):
    manager = ProjectWorkspaceManager()
    project_id = "selector-test"
    manager.write_project_file(project_id, "website/templates/index.html", "<h1>Home</h1>\n", "Test", "run-1", "home")
    manager.write_project_file(project_id, "website/templates/status.html", "<h1>Status</h1>\n", "Test", "run-1", "status")
    manager.write_project_file(project_id, "website/app.py", "print('ok')\n", "Test", "run-1", "app")
    manager.write_project_file(project_id, "website/data/order_statuses.json", "[]\n", "Test", "run-1", "status data")
    file_map = ProjectInspector().file_map(project_id)

    homepage = select_relevant_files(
        command="Improve homepage copy",
        task_type=classify_task("Improve homepage copy"),
        file_map=file_map,
        max_files=3,
    )
    assert "website/templates/index.html" in [item.path for item, _reason in homepage]

    status = select_relevant_files(
        command="Fix order status page",
        task_type=classify_task("Fix order status page"),
        file_map=file_map,
        max_files=4,
    )
    paths = [item.path for item, _reason in status]
    assert "website/templates/status.html" in paths
    assert "website/app.py" in paths


def test_patch_validation_rejects_unsafe_and_accepts_valid(client):
    validator = PatchApplier()
    traversal = ProposedPatch(
        summary="bad",
        task_type="website_copy_update",
        files_to_change=[CodingFileChange(path="../outside.txt", reason="bad", new_content="bad")],
    )
    assert validator.validate(traversal, task_type="website_copy_update").accepted is False

    env_write = ProposedPatch(
        summary="bad",
        task_type="website_copy_update",
        files_to_change=[CodingFileChange(path=".env", reason="bad", new_content="OPENAI_API_KEY=sk-secret")],
    )
    assert validator.validate(env_write, task_type="website_copy_update").accepted is False

    valid = ProposedPatch(
        summary="ok",
        task_type="website_copy_update",
        files_to_change=[CodingFileChange(path="website/templates/index.html", reason="copy", new_content="<h1>Better</h1>\n")],
    )
    assert validator.validate(valid, task_type="website_copy_update").accepted is True


def test_patch_validation_enforces_exact_prompt_scope(client):
    validator = PatchApplier()
    scope = prompt_file_scope("Improve only the hero. Only edit website/templates/index.html.")
    valid = ProposedPatch(
        summary="ok",
        task_type="website_copy_update",
        files_to_change=[CodingFileChange(path="website/templates/index.html", reason="copy", new_content="<h1>Better</h1>\n")],
    )
    rejected = ProposedPatch(
        summary="bad",
        task_type="website_copy_update",
        files_to_change=[CodingFileChange(path="website/data/faqs.json", reason="extra", new_content="[]\n")],
    )
    assert validator.validate(valid, task_type="website_copy_update", file_scope=scope).accepted is True
    result = validator.validate(rejected, task_type="website_copy_update", file_scope=scope)
    assert result.accepted is False
    assert "Outside prompt-level exact_file scope" in " ".join(result.violations)


def test_homepage_content_scope_blocks_backend_and_order_files(client):
    validator = PatchApplier()
    scope = prompt_file_scope("Use memory to improve homepage copy. Only update homepage/content files.")
    patch = ProposedPatch(
        summary="too broad",
        task_type="website_copy_update",
        files_to_change=[
            CodingFileChange(path="website/templates/index.html", reason="copy", new_content="<h1>Better</h1>\n"),
            CodingFileChange(path="website/app.py", reason="unneeded", new_content="print('bad')\n"),
            CodingFileChange(path="website/requirements.txt", reason="unneeded", new_content="flask\n"),
            CodingFileChange(path="website/data/sample_orders.json", reason="unneeded", new_content="[]\n"),
            CodingFileChange(path="website/templates/status.html", reason="unneeded", new_content="<h1>Status</h1>\n"),
            CodingFileChange(path="website/data/order_statuses.json", reason="unneeded", new_content="[]\n"),
        ],
    )
    result = validator.validate(patch, task_type="website_copy_update", file_scope=scope)
    assert result.accepted is False
    joined = " ".join(result.violations)
    assert "website/app.py" in joined
    assert "website/requirements.txt" in joined
    assert "website/data/sample_orders.json" in joined
    assert "website/templates/status.html" in joined
    assert "website/data/order_statuses.json" in joined


def test_website_update_uses_real_coding_agent_in_mock(client):
    seed = client.post(
        "/api/runs",
        json={
            "command": "Create a simple Greek yogurt order website prototype with files.",
            "mode": "mock",
            "run_type": "prototype_build",
            "project_id": "greek-yogurt-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
        },
    )
    assert seed.status_code == 200
    response = client.post(
        "/api/runs",
        json={
            "command": "Improve homepage copy. Only update homepage/content files. No web search. Do not deploy. Do not install packages.",
            "mode": "mock",
            "run_type": "website_update",
            "project_id": "greek-yogurt-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_live_coding_model_call": False,
            "real_coding_dry_run": False,
            "real_coding_model": "moonshotai/kimi-k2.7-code",
        },
    )
    assert response.status_code == 200
    run = response.json()
    detail = run["usage_summary"]["real_coding_agent"]
    assert detail["used"] is True
    assert detail["actual_provider"] == "mock"
    assert detail["mock_simulated"] is True
    assert detail["live_call_made"] is False
    assert detail["hardcoded_fallback_used"] is False
    assert detail["selected_model"] == "moonshotai/kimi-k2.7-code"
    assert detail["allowed_user_file_scope"]["scope_type"] == "homepage_content"
    changed = set(run["project_files_created"] + run["project_files_updated"])
    assert "website/templates/index.html" in changed
    assert "website/app.py" not in changed
    assert any(artifact["name"] == "real_coding_agent_report.md" for artifact in run["artifacts"])
    assert all(event["agent_name"] != "Website Agent" for event in run["events"])


def test_focused_homepage_prompt_normalizes_prototype_build_to_real_coding_website_update(client):
    manager = ProjectWorkspaceManager()
    manager.write_project_file("route-test", "website/templates/index.html", "<section><h1>Before</h1></section>\n", "Test", "seed", "home")
    response = client.post(
        "/api/runs",
        json={
            "command": "Improve only the homepage hero headline and subheadline using previous memory. Only edit website/templates/index.html. Do not deploy. Do not install packages. Do not use GPT-5.5. Do not run live web search.",
            "mode": "mock",
            "run_type": "prototype_build",
            "project_id": "route-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert run["run_type"] == "website_update"
    assert run["usage_summary"]["selected_workflow"] == "website_update"
    detail = run["usage_summary"]["real_coding_agent"]
    assert detail["used"] is True
    assert detail["hardcoded_fallback_used"] is False
    assert detail["selected_model"] == "moonshotai/kimi-k2.7-code"
    assert detail["fallback_model"] == "qwen/qwen3-coder"
    assert detail["allowed_user_file_scope"]["scope_type"] == "exact_file"
    changed = set(run["project_files_created"] + run["project_files_updated"])
    assert changed == {"website/templates/index.html"}
    models = set(run["models_used"])
    assert "gpt-5.5" not in models
    assert all(not event["model_used"].startswith("gpt-5.5") for event in run["events"])
    assert all(event["agent_name"] != "File Builder Agent" for event in run["events"])


def test_template_fallback_marked_when_real_coding_disabled(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Improve homepage copy. Only update homepage/content files. Do not deploy. Do not install packages.",
            "mode": "mock",
            "run_type": "website_update",
            "project_id": "fallback-test",
            "allow_file_writes": True,
            "allow_safe_commands": False,
            "use_real_coding_agent": False,
        },
    )
    assert response.status_code == 200
    run = response.json()
    detail = run["usage_summary"]["real_coding_agent"]
    assert detail["used"] is False
    assert detail["hardcoded_fallback_used"] is True
    assert any("Template fallback used" in event["output_summary"] for event in run["events"] if event["agent_name"] == "Website Agent")


def test_real_coding_dry_run_validates_without_applying(client):
    manager = ProjectWorkspaceManager()
    manager.write_project_file("dry-run-test", "website/templates/index.html", "<h1>Before</h1>\n", "Test", "seed", "home")
    response = client.post(
        "/api/runs",
        json={
            "command": "Improve homepage copy. Only update homepage/content files. No web search.",
            "mode": "mock",
            "run_type": "website_update",
            "project_id": "dry-run-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "real_coding_dry_run": True,
        },
    )
    assert response.status_code == 200
    run = response.json()
    detail = run["usage_summary"]["real_coding_agent"]
    assert detail["dry_run"] is True
    assert detail["validation"]["accepted"] is True
    assert detail["proposed_patch"]["files_to_change"]
    assert detail["patch_applied"] is False
    assert run["project_files_created"] == []
    assert run["project_files_updated"] == []
    assert "Before" in manager.read_project_file("dry-run-test", "website/templates/index.html")


def test_exact_file_explicit_replacement_applies_only_index(client):
    manager = ProjectWorkspaceManager()
    manager.write_project_file("exact-apply-test", "website/templates/index.html", "<section><h1>Old</h1><p>Old sub</p></section>\n", "Test", "seed", "home")
    response = client.post(
        "/api/runs",
        json={
            "command": "Only edit website/templates/index.html.\n\nReplace the homepage hero headline with exactly:\n“High-Protein Greek Yogurt, Made for Your Everyday Routine”\n\nReplace the hero subheadline with exactly:\n“Thick, satisfying yogurt with a simple, premium feel.”\n\nDo not change any other file. Do not deploy. Do not install packages. Do not use GPT-5.5. Do not run live web search.",
            "mode": "mock",
            "run_type": "prototype_build",
            "project_id": "exact-apply-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    run = response.json()
    detail = run["usage_summary"]["real_coding_agent"]
    assert run["run_type"] == "website_update"
    assert detail["patch_applied"] is True
    assert detail["dry_run"] is False
    assert detail["allowed_user_file_scope"]["scope_type"] == "exact_file"
    assert set(run["project_files_created"] + run["project_files_updated"]) == {"website/templates/index.html"}
    content = manager.read_project_file("exact-apply-test", "website/templates/index.html")
    assert "High-Protein Greek Yogurt, Made for Your Everyday Routine" in content
    assert "Thick, satisfying yogurt with a simple, premium feel." in content
    assert all(event["agent_name"] != "File Builder Agent" for event in run["events"])


def test_exact_file_explicit_replacement_dry_run_applies_no_user_files(client):
    manager = ProjectWorkspaceManager()
    manager.write_project_file("exact-dry-test", "website/templates/index.html", "<section><h1>Old</h1><p>Old sub</p></section>\n", "Test", "seed", "home")
    response = client.post(
        "/api/runs",
        json={
            "command": "Only edit website/templates/index.html.\n\nReplace the homepage hero headline with exactly:\n“High-Protein Greek Yogurt, Made for Your Everyday Routine”\n\nReplace the hero subheadline with exactly:\n“Thick, satisfying yogurt with a simple, premium feel.”\n\nDo not change any other file. Do not deploy. Do not install packages. Do not use GPT-5.5. Do not run live web search.",
            "mode": "mock",
            "run_type": "prototype_build",
            "project_id": "exact-dry-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_web_search": False,
            "real_coding_dry_run": True,
        },
    )
    assert response.status_code == 200
    run = response.json()
    detail = run["usage_summary"]["real_coding_agent"]
    assert detail["dry_run"] is True
    assert detail["patch_applied"] is False
    assert detail["proposed_patch"]["files_to_change"]
    assert run["project_files_created"] == []
    assert run["project_files_updated"] == []
    assert "Old" in manager.read_project_file("exact-dry-test", "website/templates/index.html")


def test_noop_exact_file_update_reports_no_change_reason(client):
    manager = ProjectWorkspaceManager()
    manager.write_project_file("noop-test", "website/templates/index.html", "<h1>Ready</h1>\n<!-- Real Coding Agent memory note: already updated -->\n", "Test", "seed", "home")
    response = client.post(
        "/api/runs",
        json={
            "command": "Update homepage copy. Only edit website/templates/index.html. Do not deploy. Do not install packages. Do not use GPT-5.5. Do not run live web search.",
            "mode": "mock",
            "run_type": "prototype_build",
            "project_id": "noop-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    run = response.json()
    detail = run["usage_summary"]["real_coding_agent"]
    assert detail["patch_applied"] is False
    assert detail["no_change_reason"]
    qa_artifact = next(artifact for artifact in run["artifacts"] if artifact["name"] == "qa_review.md")
    qa_content = client.get(f"/api/runs/{run['run_id']}/artifacts/{qa_artifact['id']}").json()["content"]
    assert "# Website Update QA Review" in qa_content
    assert "No user-facing file changes were applied because" in qa_content
    assert "research-only workflow" not in qa_content


def test_website_update_qa_wording_for_applied_and_dry_run(client):
    manager = ProjectWorkspaceManager()
    manager.write_project_file("qa-applied-test", "website/templates/index.html", "<section><h1>Old</h1><p>Old sub</p></section>\n", "Test", "seed", "home")
    response = client.post(
        "/api/runs",
        json={
            "command": "Only edit website/templates/index.html. Replace the homepage hero headline with exactly:\n“Fresh Greek Yogurt”\n\nDo not deploy. Do not install packages. Do not use GPT-5.5. Do not run live web search.",
            "mode": "mock",
            "run_type": "prototype_build",
            "project_id": "qa-applied-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    run = response.json()
    qa_artifact = next(artifact for artifact in run["artifacts"] if artifact["name"] == "qa_review.md")
    qa_content = client.get(f"/api/runs/{run['run_id']}/artifacts/{qa_artifact['id']}").json()["content"]
    assert "# Website Update QA Review" in qa_content
    assert "Workflow: website_update" in qa_content
    assert "User-facing file changes were applied within the approved scope." in qa_content
    assert "research-only workflow" not in qa_content

    manager.write_project_file("qa-dry-test", "website/templates/index.html", "<section><h1>Old</h1><p>Old sub</p></section>\n", "Test", "seed", "home")
    dry = client.post(
        "/api/runs",
        json={
            "command": "Only edit website/templates/index.html. Replace the homepage hero headline with exactly:\n“Fresh Greek Yogurt”\n\nDo not deploy. Do not install packages. Do not use GPT-5.5. Do not run live web search.",
            "mode": "mock",
            "run_type": "prototype_build",
            "project_id": "qa-dry-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_web_search": False,
            "real_coding_dry_run": True,
        },
    )
    assert dry.status_code == 200
    dry_run = dry.json()
    dry_qa_artifact = next(artifact for artifact in dry_run["artifacts"] if artifact["name"] == "qa_review.md")
    dry_qa_content = client.get(f"/api/runs/{dry_run['run_id']}/artifacts/{dry_qa_artifact['id']}").json()["content"]
    assert "dry run was enabled" in dry_qa_content


def test_rejected_patch_qa_explains_validation_reason(client):
    result = RealCodingAgentResult(
        enabled=True,
        used=True,
        actual_provider="mock",
        selected_model="moonshotai/kimi-k2.7-code",
        fallback_model="qwen/qwen3-coder",
        task_type="website_copy_update",
        validation=PatchValidationResult(accepted=False, violations=["website/app.py: Outside prompt-level exact_file scope."]),
    )
    qa = ExecutionEngine()._prototype_qa_review(
        "Only edit website/templates/index.html",
        "qa input",
        [],
        file_changes_count=0,
        workflow="website_update",
        real_coding_result=result,
    )
    assert "# Website Update QA Review" in qa
    assert "proposed patch was rejected by validation" in qa
    assert "website/app.py" in qa


def test_research_only_keeps_research_qa_wording(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: Greek yogurt competitor themes. Do not update files.",
            "mode": "mock",
            "run_type": "research_only",
            "project_id": "research-qa-test",
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    run = response.json()
    qa_artifact = next(artifact for artifact in run["artifacts"] if artifact["name"] == "qa_review.md")
    qa_content = client.get(f"/api/runs/{run['run_id']}/artifacts/{qa_artifact['id']}").json()["content"]
    assert "# Research QA Review" in qa_content
    assert "Workflow: research_only" in qa_content


def test_coding_context_prioritizes_live_source_memory_and_excludes_noise(client):
    store = MemoryStore()
    store.add_item(
        {
            "project_id": "memory-context-test",
            "memory_type": "research_source_summary",
            "title": "Skipped search summary",
            "summary": "No source search happened.",
            "content": "Skipped source collection.",
            "source_type": "search_source",
            "tags": ["research", "sources", "competitors"],
            "allowed_agents": ["website_agent"],
            "metadata": {"source_count": 0, "search_unavailable": True},
        }
    )
    store.add_item(
        {
            "project_id": "memory-context-test",
            "memory_type": "qa_warning",
            "title": "Generic old warning",
            "summary": "Old no-op warning unrelated to scope.",
            "content": "Old no-op warning unrelated to scope.",
            "source_type": "artifact",
            "tags": ["qa"],
            "allowed_agents": ["website_agent"],
        }
    )
    live = store.add_item(
        {
            "project_id": "memory-context-test",
            "memory_type": "research_source_summary",
            "title": "Live Exa source summary",
            "summary": "Live source-backed competitor research.",
            "content": "Source-backed research for market positioning.",
            "source_type": "search_source",
            "source_run_id": "live-source-run",
            "tags": ["research", "sources", "exa_direct", "competitors"],
            "allowed_agents": ["website_agent"],
            "search_provider": "exa_direct",
            "source_urls": ["https://example.com/source"],
            "metadata": {"source_count": 5, "search_unavailable": False, "mock_fixture": False, "provider_id": "exa_direct"},
            "importance": 4,
        }
    )
    manager = ProjectWorkspaceManager()
    manager.write_project_file("memory-context-test", "website/templates/index.html", "<h1>Home</h1>\n", "Test", "seed", "home")
    packet = build_context_packet(
        agent_id="website_agent",
        project_id="memory-context-test",
        run_id="memory-test",
        run_type="website_update",
        task="homepage copy competitor research",
        current_command="Use previous competitor research from memory to improve homepage copy.",
    )
    context = CodingContextBuilder().build(
        project_id="memory-context-test",
        run_id="memory-test",
        command="Use previous competitor research from memory to improve homepage copy. Only update homepage/content files.",
        task_type="website_copy_update",
        max_files=4,
        memory_packet=packet,
    )
    assert context.memory_used[0]["source_run_id"] == live.source_run_id
    assert context.memory_used[0]["source_count"] == 5
    assert any(item["type"] == "memory_filter_note" for item in context.memory_used)
    assert context.allowed_user_file_scope.scope_type == "homepage_content"


def test_validation_reporting_separates_patch_and_project_sanity(client):
    manager = ProjectWorkspaceManager()
    manager.write_project_file("validation-report-test", "website/templates/index.html", "<section><h1>Old</h1><p>Old sub</p></section>\n", "Test", "seed", "home")
    manager.write_project_file("validation-report-test", "website/app.py", "print('ok')\n", "Test", "seed", "app")
    response = client.post(
        "/api/runs",
        json={
            "command": "Only edit website/templates/index.html. Replace the homepage hero headline with exactly:\n“Fresh Greek Yogurt”\n\nDo not deploy. Do not install packages. Do not use GPT-5.5. Do not run live web search.",
            "mode": "mock",
            "run_type": "prototype_build",
            "project_id": "validation-report-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    run = response.json()
    detail = run["usage_summary"]["real_coding_agent"]
    sanity = run["usage_summary"]["project_sanity_validation"]
    assert detail["validation"]["accepted"] is True
    assert detail["validation_commands"] == []
    assert sanity["safe_commands_executed"] == 1
    assert "does not directly validate unchanged HTML/JSON copy" in sanity["reason"]


def test_live_real_coding_call_blocked_without_flags(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Improve homepage copy.",
            "mode": "live",
            "run_type": "website_update",
            "project_id": "live-block-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "use_real_coding_agent": True,
            "allow_live_coding_model_call": True,
            "max_cost_usd": 0.05,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approval_required"
    assert any(item["approval_type"] == "live_coding_model" for item in payload["approval_requests"])
