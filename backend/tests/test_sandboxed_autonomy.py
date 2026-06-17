import pytest
from fastapi import HTTPException

from app.memory.embedding_memory import EmbeddingMemory
from app.workspace.command_runner import SafeCommandRunner
from app.workspace.file_writer import WorkspaceFileWriter


PROTOTYPE_COMMAND = "Create a simple Greek yogurt order website prototype with files."


def test_workspace_file_writer_allows_safe_files_and_updates_manifest(client):
    writer = WorkspaceFileWriter()
    entry = writer.write_file("run-safe", "generated/demo/README.md", "# Demo\n", "Test Agent", "Demo file")

    assert entry.operation in {"created", "updated"}
    assert entry.path == "generated/demo/README.md"
    assert "generated/demo/README.md" in writer.list_files("run-safe")
    assert writer.read_file("run-safe", "generated/demo/README.md") == "# Demo\n"


@pytest.mark.parametrize("path", ["../../escape.md", ".env", "generated/demo/.env", "generated/demo/file.exe"])
def test_workspace_file_writer_blocks_unsafe_paths(client, path):
    writer = WorkspaceFileWriter()
    with pytest.raises(HTTPException):
        writer.write_file("run-blocked", path, "bad", "Test Agent")


def test_safe_command_runner_allows_py_compile_and_blocks_dangerous_commands(client):
    writer = WorkspaceFileWriter()
    writer.write_file("run-command", "generated/demo/app.py", "print('ok')\n", "Test Agent")
    runner = SafeCommandRunner()

    allowed = runner.run_safe_command("run-command", ["python", "-m", "py_compile", "generated/demo/app.py"])
    assert allowed.allowed is True
    assert allowed.exit_code == 0

    blocked = runner.run_safe_command("run-command", ["rm", "-rf", "."])
    assert blocked.allowed is False
    assert "blocked" in blocked.blocked_reason


def test_prototype_build_creates_workspace_files_artifacts_commands_and_memory(client):
    response = client.post(
        "/api/runs",
        json={
            "command": PROTOTYPE_COMMAND,
            "mode": "mock",
            "project_id": "greek-yogurt-test",
            "run_type": "prototype_build",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "allow_ceo_live": False,
            "max_cost_usd": 0.25,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    run_id = payload["run_id"]
    workspace = payload["workspace"]

    assert payload["status"] == "completed"
    assert workspace["root"] == "backend/data/projects/greek-yogurt-test"
    assert payload["project_workspace"]["root"] == "backend/data/projects/greek-yogurt-test"
    assert "website/app.py" in workspace["files_created"]
    assert "website/templates/index.html" in workspace["files_created"]
    assert workspace["commands_run"][0]["allowed"] is True
    assert workspace["commands_run"][0]["exit_code"] == 0
    assert payload["memory_updates"]

    artifacts = client.get(f"/api/runs/{run_id}/artifacts").json()
    artifact_types = {artifact["type"] for artifact in artifacts}
    assert "project_file" in artifact_types
    assert "project_manifest" in artifact_types
    assert "project_state" in artifact_types
    assert "command_log" in artifact_types
    assert "prototype_project" in artifact_types

    files = client.get("/api/projects/greek-yogurt-test/files").json()
    assert any(file["path"] == "website/app.py" for file in files)

    app_file = client.get("/api/projects/greek-yogurt-test/files/website/app.py")
    assert app_file.status_code == 200
    assert "HTTPServer" in app_file.json()["content"]

    manifest = client.get("/api/projects/greek-yogurt-test/manifest").json()
    assert any(item["path"] == "website/app.py" for item in manifest["files"])
    assert any(item["run_id"] == run_id for item in manifest["runs"])

    commands = payload["workspace"]["commands_run"]
    assert commands[0]["command"] == ["python", "-m", "py_compile", "website/app.py"]
    command_endpoint = client.get(f"/api/runs/{run_id}/commands")
    assert command_endpoint.status_code == 200
    assert command_endpoint.json()[0]["command"] == ["python", "-m", "py_compile", "website/app.py"]

    blocked_env = client.get("/api/projects/greek-yogurt-test/files/.env")
    assert blocked_env.status_code == 400

    memories = EmbeddingMemory().search_memory("Greek yogurt prototype files", filters={"run_id": run_id})
    assert memories


def test_prototype_build_continuation_updates_persistent_project(client):
    first = client.post(
        "/api/runs",
        json={
            "command": PROTOTYPE_COMMAND,
            "mode": "mock",
            "project_id": "greek-yogurt-test",
            "run_type": "prototype_build",
            "allow_file_writes": True,
            "allow_safe_commands": True,
        },
    )
    assert first.status_code == 200
    second = client.post(
        "/api/runs",
        json={
            "command": "Continue the Greek yogurt website and add a simple order status page.",
            "mode": "mock",
            "project_id": "greek-yogurt-test",
            "run_type": "prototype_build",
            "allow_file_writes": True,
            "allow_safe_commands": True,
        },
    )
    assert second.status_code == 200
    second_payload = second.json()

    assert "website/app.py" in second_payload["workspace"]["files_edited"]
    assert "website/templates/status.html" in second_payload["workspace"]["files_created"]
    assert "website/data/order_statuses.json" in second_payload["workspace"]["files_created"]
    assert "generated/greek_yogurt_site" not in "\n".join(second_payload["workspace"]["files_created"])

    manifest = client.get("/api/projects/greek-yogurt-test/manifest").json()
    paths = {item["path"] for item in manifest["files"]}
    assert "website/app.py" in paths
    assert "website/templates/status.html" in paths
    assert len(manifest["runs"]) == 2

    state = client.get("/api/projects/greek-yogurt-test/state").json()["content"]
    assert second_payload["run_id"] in state

    changes = client.get("/api/projects/greek-yogurt-test/changes").json()["changes"]
    assert any(change["path"] == "website/app.py" and change["operation"] == "updated" for change in changes)

    traversal = client.get("/api/projects/greek-yogurt-test/files/../../.env")
    assert traversal.status_code in {400, 404}


def test_continuation_run_type_uses_project_file_workflow(client):
    first = client.post(
        "/api/runs",
        json={
            "command": PROTOTYPE_COMMAND,
            "mode": "mock",
            "project_id": "greek-yogurt-test",
            "run_type": "prototype_build",
            "allow_file_writes": True,
            "allow_safe_commands": True,
        },
    )
    assert first.status_code == 200
    first_payload = first.json()

    continuation = client.post(
        "/api/runs",
        json={
            "command": "Continue the Greek yogurt website and add a small FAQ section.",
            "mode": "mock",
            "project_id": "greek-yogurt-test",
            "run_type": "continuation",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "allow_ceo_live": False,
            "max_cost_usd": 0.25,
        },
    )
    assert continuation.status_code == 200
    payload = continuation.json()
    run_id = payload["run_id"]

    assert payload["run_type"] == "continuation"
    assert payload["project_id"] == "greek-yogurt-test"
    assert payload["project_workspace"]["root"] == "backend/data/projects/greek-yogurt-test"
    assert first_payload["project_workspace"]["root"] == payload["project_workspace"]["root"]
    assert any(event["agent_name"] == "File Builder Agent" for event in payload["events"])
    assert any(event["agent_name"] == "Safe Command Runner" for event in payload["events"])
    assert payload["workspace"]["commands_run"][0]["command"] == ["python", "-m", "py_compile", "website/app.py"]
    assert payload["workspace"]["commands_run"][0]["exit_code"] == 0
    assert payload["commands_run"][0]["exit_code"] == 0
    assert payload["project_files_created"] or payload["project_files_updated"]
    assert "website/templates/index.html" in payload["project_files_updated"]
    assert "website/data/faqs.json" in payload["project_files_created"]

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["commands_run"]
    assert detail_payload["project_files_created"] or detail_payload["project_files_updated"]

    command_endpoint = client.get(f"/api/runs/{run_id}/commands")
    assert command_endpoint.status_code == 200
    assert command_endpoint.json()[0]["allowed"] is True

    files = client.get("/api/projects/greek-yogurt-test/files").json()
    paths = {file["path"] for file in files}
    assert "website/data/faqs.json" in paths
    assert "website/templates/index.html" in paths

    index = client.get("/api/projects/greek-yogurt-test/files/website/templates/index.html")
    assert index.status_code == 200
    assert "FAQ" in index.json()["content"]

    changes = client.get("/api/projects/greek-yogurt-test/changes").json()["changes"]
    continuation_changes = [change for change in changes if change["run_id"] == run_id]
    assert any(change["path"] == "website/templates/index.html" for change in continuation_changes)
    assert any(change["path"] == "website/data/faqs.json" for change in continuation_changes)

    refresh = client.post(
        "/api/runs",
        json={
            "command": PROTOTYPE_COMMAND,
            "mode": "mock",
            "project_id": "greek-yogurt-test",
            "run_type": "prototype_build",
            "allow_file_writes": True,
            "allow_safe_commands": True,
        },
    )
    assert refresh.status_code == 200
    refresh_payload = refresh.json()
    assert "website/templates/index.html" in refresh_payload["project_files_updated"]

    refreshed_index = client.get("/api/projects/greek-yogurt-test/files/website/templates/index.html")
    assert refreshed_index.status_code == 200
    refreshed_content = refreshed_index.json()["content"]
    assert "FAQ" in refreshed_content
    assert "/status?order_id=GY-1001" in refreshed_content

    refreshed_app = client.get("/api/projects/greek-yogurt-test/files/website/app.py")
    assert refreshed_app.status_code == 200
    assert "def _status_payload" in refreshed_app.json()["content"]


def test_prototype_build_requires_file_write_approval(client):
    response = client.post(
        "/api/runs",
        json={
            "command": PROTOTYPE_COMMAND,
            "mode": "mock",
            "run_type": "prototype_build",
            "allow_file_writes": False,
            "allow_safe_commands": True,
        },
    )
    assert response.status_code == 403
    assert "allow_file_writes=true" in response.text


def test_business_launch_plan_still_works(client):
    response = client.post("/api/runs", json={"command": "Plan a safe launch", "mode": "mock"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_type"] == "business_launch_plan"
    assert not any(event["agent_name"] == "File Builder Agent" for event in payload["events"])
    assert payload["project_files_created"] == []
    assert payload["project_files_updated"] == []
    assert payload["commands_run"] == []
