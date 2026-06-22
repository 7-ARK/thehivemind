import json

from app.memory.context_packet import build_context_packet, format_context_packet
from app.memory.memory_retriever import MemoryRetriever
from app.memory.memory_store import MemoryStore
from app.memory.schemas import MemoryRetrievalRequest


def test_memory_item_store_redacts_secrets(client):
    item = MemoryStore().add_item(
        {
            "project_id": "proj-a",
            "memory_type": "qa_warning",
            "title": "Secret test",
            "summary": "api_key=sk-secret-secret-secret",
            "content": "password=hunter2",
            "source_type": "manual",
        }
    )
    assert "[REDACTED_SECRET]" in item.summary
    assert "hunter2" not in item.content
    assert item.is_sensitive is True


def test_memory_retrieval_project_scoped_and_explainable(client):
    store = MemoryStore()
    store.add_item(
        {
            "project_id": "greek-yogurt-test",
            "memory_type": "research_source_summary",
            "title": "Greek yogurt competitors",
            "summary": "Exa found Chobani, FAGE, Oikos, and Danone competitor themes.",
            "content": "Greek yogurt competitor research from Exa.",
            "source_type": "search_source",
            "tags": ["greek-yogurt-test", "competitors", "exa"],
            "source_urls": ["https://example.com/source"],
            "allowed_agents": ["research_agent", "website_agent", "qa_agent"],
            "importance": 4,
        }
    )
    store.add_item(
        {
            "project_id": "other-project",
            "memory_type": "research_brief",
            "title": "Other project",
            "summary": "Should not leak to greek yogurt project.",
            "content": "Unrelated.",
            "source_type": "artifact",
        }
    )
    results = MemoryRetriever().retrieve(
        MemoryRetrievalRequest(project_id="greek-yogurt-test", query="Greek yogurt competitors", agent_id="research_agent", run_type="research_only")
    )
    assert results
    assert all(result.item.project_id in (None, "greek-yogurt-test") for result in results)
    assert any(result.why_selected for result in results)
    assert any(result.item.memory_type == "research_source_summary" for result in results)


def test_context_packet_contains_constraints_and_no_secrets(client):
    MemoryStore().add_item(
        {
            "project_id": "greek-yogurt-test",
            "memory_type": "model_selection",
            "title": "Routing",
            "summary": "Use cheap models. token=sk-super-secret-secret",
            "content": "GPT-5.5 remains gated.",
            "source_type": "model_selection",
            "tags": ["models"],
        }
    )
    packet = build_context_packet(
        agent_id="research_agent",
        project_id="greek-yogurt-test",
        run_id="run-1",
        run_type="research_only",
        task="Greek yogurt research",
        current_command="Research only. Do not use GPT-5.5. Do not update files.",
    )
    rendered = format_context_packet(packet)
    assert "Do not update files" in rendered
    assert "GPT-5.5" in rendered
    assert "sk-super" not in rendered


def test_memory_api_status_search_rebuild_and_context(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: Greek yogurt competitor themes. Do not update files.",
            "mode": "mock",
            "run_type": "research_only",
            "project_id": "greek-yogurt-test",
            "allow_web_search": False,
            "use_memory": True,
        },
    )
    assert response.status_code == 200
    run = response.json()

    status = client.get("/api/memory/status").json()
    assert status["enabled"] is True
    assert status["total_memory_items"] > 0

    search = client.get("/api/memory/projects/greek-yogurt-test/search?q=competitor%20themes&agent_id=research_agent&run_type=research_only").json()
    assert "results" in search

    rebuild = client.post("/api/memory/projects/greek-yogurt-test/rebuild").json()
    assert rebuild["item_count"] >= 1

    context = client.get(f"/api/memory/runs/{run['run_id']}/context-packet?agent_id=qa_agent").json()
    assert context["active_constraints"]
    assert "retrieved_memory_items" in context


def test_research_sources_are_summarized_not_raw_files(client, monkeypatch):
    monkeypatch.setenv("ALLOW_WEB_SEARCH", "true")
    monkeypatch.setenv("ENABLE_EXA_SEARCH", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: latest Greek yogurt competitors.",
            "mode": "mock",
            "run_type": "research_only",
            "project_id": "greek-yogurt-test",
            "allow_web_search": True,
            "use_memory": True,
        },
    )
    assert response.status_code == 200
    items = client.get("/api/memory/projects/greek-yogurt-test/items?memory_type=research_source_summary").json()["items"]
    assert items
    assert items[0]["metadata"]["mock_fixture"] is True
    assert items[0]["source_urls"]


def test_research_only_qa_wording_does_not_claim_file_changes(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: Greek yogurt competitors. Do not update files.",
            "mode": "mock",
            "run_type": "research_only",
            "project_id": "greek-yogurt-test",
            "allow_web_search": False,
        },
    )
    run = response.json()
    qa_artifact = next(artifact for artifact in run["artifacts"] if artifact["name"] == "qa_review.md")
    content = client.get(f"/api/runs/{run['run_id']}/artifacts/{qa_artifact['id']}").json()["content"]
    assert "# Research QA Review" in content
    assert "No user-facing project files were updated because this was a research-only workflow." in content
    assert "Project files were generated or updated" not in content
    assert "No new live search was run because search was unavailable/skipped" in content


def test_research_only_report_uses_previous_source_memory(client):
    MemoryStore().add_item(
        {
            "project_id": "greek-yogurt-test",
            "memory_type": "research_source_summary",
            "title": "Previous live Exa Greek yogurt research",
            "summary": "Live Exa found Chobani, Danone/Oikos, FAGE, Muller, Nestle, Yoplait, Lactalis, protein, and clean-label competitor themes.",
            "content": "Chobani and Danone Oikos compete on high protein. FAGE is authentic premium. Muller, Nestle, Yoplait, and Lactalis appear in broader yogurt competition.",
            "source_type": "search_source",
            "source_run_id": "309ce14b-42c0-454f-a530-d23edd45e0a7",
            "tags": ["research", "sources", "exa_direct", "competitors"],
            "importance": 4,
            "allowed_agents": ["research_agent", "website_agent", "qa_agent"],
            "search_provider": "exa_direct",
            "source_urls": ["https://example.com/chobani"],
            "metadata": {"source_count": 5, "mock_fixture": False, "search_unavailable": False, "provider_id": "exa_direct", "search_used": True},
        }
    )
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: use previous Greek yogurt competitor research from memory and summarize the top competitor themes. Do not update files. No web search.",
            "mode": "mock",
            "run_type": "research_only",
            "project_id": "greek-yogurt-test",
            "allow_web_search": False,
            "use_memory": True,
        },
    )
    assert response.status_code == 200
    run = response.json()
    research_artifact = next(artifact for artifact in run["artifacts"] if artifact["name"] == "research_brief.md")
    content = client.get(f"/api/runs/{run['run_id']}/artifacts/{research_artifact['id']}").json()["content"]
    assert "## Memory Used" in content
    assert "309ce14b-42c0-454f-a530-d23edd45e0a7" in content
    assert "## Competitor Themes From Memory" in content
    assert "Chobani" in content
    assert "FAGE" in content
    assert "No new live search was run" in content


def test_retrieval_live_source_memory_outranks_skipped_and_planning(client):
    store = MemoryStore()
    skipped = store.add_item(
        {
            "project_id": "greek-yogurt-test",
            "memory_type": "research_source_summary",
            "title": "Skipped search",
            "summary": "Greek yogurt competitors but search was skipped.",
            "content": "No live search was run for Greek yogurt competitors.",
            "source_type": "search_source",
            "tags": ["research", "sources", "competitors"],
            "allowed_agents": ["research_agent", "website_agent", "qa_agent"],
            "metadata": {"source_count": 0, "search_unavailable": True, "mock_fixture": False},
        }
    )
    plan = store.add_item(
        {
            "project_id": "greek-yogurt-test",
            "memory_type": "agent_plan",
            "title": "Planning record",
            "summary": "Plan Greek yogurt competitor research workflow.",
            "content": "Agent plan for Greek yogurt competitors.",
            "source_type": "artifact",
            "tags": ["planner", "competitors"],
            "allowed_agents": ["research_agent", "website_agent", "qa_agent"],
            "importance": 4,
        }
    )
    live = store.add_item(
        {
            "project_id": "greek-yogurt-test",
            "memory_type": "research_source_summary",
            "title": "Live Exa source record",
            "summary": "Live Exa sources for Greek yogurt competitors including Chobani and FAGE.",
            "content": "Chobani, Oikos, Danone, and FAGE Greek yogurt competitor sources.",
            "source_type": "search_source",
            "source_run_id": "live-run",
            "tags": ["research", "sources", "exa_direct", "competitors"],
            "allowed_agents": ["research_agent", "website_agent", "qa_agent"],
            "search_provider": "exa_direct",
            "source_urls": ["https://example.com/live"],
            "metadata": {"source_count": 5, "search_unavailable": False, "mock_fixture": False, "provider_id": "exa_direct"},
            "importance": 4,
        }
    )
    results = MemoryRetriever().retrieve(
        MemoryRetrievalRequest(project_id="greek-yogurt-test", query="homepage copy competitor research", agent_id="research_agent", run_type="research_only")
    )
    assert results[0].item.id == live.id
    assert results.index(next(result for result in results if result.item.id == live.id)) < results.index(next(result for result in results if result.item.id == skipped.id))
    plan_result = next((result for result in results if result.item.id == plan.id), None)
    if plan_result is not None:
        assert results.index(next(result for result in results if result.item.id == live.id)) < results.index(plan_result)
    assert "boosted: source_count > 0" in results[0].why_selected
    assert "boosted: previous live Exa source" in results[0].why_selected


def test_homepage_copy_scope_limits_user_facing_file_changes(client):
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
    MemoryStore().add_item(
        {
            "project_id": "greek-yogurt-test",
            "memory_type": "research_source_summary",
            "title": "Previous live Exa Greek yogurt research",
            "summary": "Chobani, Oikos, FAGE, protein, and clean-label themes.",
            "content": "Chobani, Oikos, Danone, FAGE, high protein, clean-label ingredients.",
            "source_type": "search_source",
            "source_run_id": "309ce14b-42c0-454f-a530-d23edd45e0a7",
            "tags": ["research", "sources", "exa_direct", "competitors"],
            "allowed_agents": ["research_agent", "website_agent", "qa_agent"],
            "search_provider": "exa_direct",
            "source_urls": ["https://example.com/source"],
            "metadata": {"source_count": 4, "mock_fixture": False, "search_unavailable": False, "provider_id": "exa_direct"},
        }
    )
    response = client.post(
        "/api/runs",
        json={
            "command": "Use previous Exa competitor research from memory to improve homepage copy. Only update homepage copy/content files. Do not deploy. Do not install packages. No web search.",
            "mode": "mock",
            "run_type": "website_update",
            "project_id": "greek-yogurt-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "allow_web_search": False,
            "use_memory": True,
        },
    )
    assert response.status_code == 200
    run = response.json()
    changed = set(run["project_files_created"] + run["project_files_updated"])
    assert "website/templates/index.html" in changed
    assert "website/data/faqs.json" in changed
    assert "website/app.py" not in changed
    assert "website/requirements.txt" not in changed
    assert "website/data/sample_orders.json" not in changed
    assert "project_state.md" not in changed
    assert run["usage_summary"]["system_metadata_files"] == ["project_state.md", "manifest.json"]

    scope_artifact = next(artifact for artifact in run["artifacts"] if artifact["name"] == "website_scope_plan.md")
    scope_content = client.get(f"/api/runs/{run['run_id']}/artifacts/{scope_artifact['id']}").json()["content"]
    assert "task_type: homepage_copy" in scope_content
    assert "website/app.py" in scope_content

    qa_artifact = next(artifact for artifact in run["artifacts"] if artifact["name"] == "qa_review.md")
    qa_content = client.get(f"/api/runs/{run['run_id']}/artifacts/{qa_artifact['id']}").json()["content"]
    assert "User-facing file changes matched prompt scope" in qa_content
    assert "System metadata was updated separately" in qa_content
    assert "Previous memory sources were used" in qa_content
