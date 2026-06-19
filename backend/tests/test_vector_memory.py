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
    assert "No project files were updated because this was a research-only workflow." in content
    assert "Project files were generated or updated" not in content
    assert "Search was unavailable/skipped" in content
