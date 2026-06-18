def _base_payload(**overrides):
    payload = {
        "command": "Continue the Greek yogurt website and add a FAQ section.",
        "mode": "mock",
        "project_id": "greek-yogurt-test",
        "run_type": "continuation",
        "allow_file_writes": True,
        "allow_safe_commands": True,
        "allow_ceo_live": False,
        "max_cost_usd": 0.25,
    }
    payload.update(overrides)
    return payload


def test_safe_mock_run_does_not_require_approval(client):
    response = client.post("/api/runs", json=_base_payload())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["run_type"] == "continuation"
    assert payload["commands_run"]


def test_live_mode_requires_approval(client):
    response = client.post("/api/runs", json=_base_payload(mode="live"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approval_required"
    assert {approval["approval_type"] for approval in payload["approval_requests"]} == {"live_mode"}


def test_allow_ceo_live_requires_approval(client):
    response = client.post("/api/runs", json=_base_payload(allow_ceo_live=True))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approval_required"
    assert any(approval["approval_type"] == "expensive_ceo_model" for approval in payload["approval_requests"])


def test_command_mentioning_gpt55_requires_approval(client):
    response = client.post(
        "/api/runs",
        json=_base_payload(command="Use GPT-5.5 as CEO and continue the Greek yogurt website."),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approval_required"
    assert any(approval["approval_type"] == "expensive_ceo_model" for approval in payload["approval_requests"])


def test_deploy_and_package_install_require_approval(client):
    response = client.post(
        "/api/runs",
        json=_base_payload(command="Deploy the Greek yogurt website live and run npm install for hosting."),
    )
    assert response.status_code == 200
    payload = response.json()
    approval_types = {approval["approval_type"] for approval in payload["approval_requests"]}
    assert "deployment" in approval_types
    assert "package_install" in approval_types


def test_approval_can_be_approved_and_used_for_resubmission(client):
    payload = _base_payload(command="Use GPT-5.5 as CEO and plan the next safe project version.")
    initial = client.post("/api/runs", json=payload)
    assert initial.status_code == 200
    approval = initial.json()["approval_requests"][0]

    decision = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approved", "reason": "Approved for this mock test."},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    payload["approval_ids"] = [approval["id"]]
    resumed = client.post("/api/runs", json=payload)
    assert resumed.status_code == 200
    resumed_payload = resumed.json()
    assert resumed_payload["status"] == "completed"
    assert resumed_payload["run_type"] == "continuation"


def test_rejected_approval_id_does_not_allow_run(client):
    payload = _base_payload(command="Use GPT-5.5 as CEO and continue the Greek yogurt website.")
    initial = client.post("/api/runs", json=payload)
    approval = initial.json()["approval_requests"][0]
    client.post(f"/api/approvals/{approval['id']}/decision", json={"decision": "rejected", "reason": "Too expensive."})

    payload["approval_ids"] = [approval["id"]]
    resumed = client.post("/api/runs", json=payload)
    assert resumed.status_code == 403
    assert "rejected" in resumed.text


def test_approval_cannot_approve_unrelated_command_or_project(client):
    payload = _base_payload(command="Use GPT-5.5 as CEO and continue the Greek yogurt website.")
    initial = client.post("/api/runs", json=payload)
    approval = initial.json()["approval_requests"][0]
    client.post(f"/api/approvals/{approval['id']}/decision", json={"decision": "approved"})

    unrelated = _base_payload(
        command="Use GPT-5.5 as CEO and continue a different project.",
        project_id="other-project",
        approval_ids=[approval["id"]],
    )
    response = client.post("/api/runs", json=unrelated)
    assert response.status_code == 403
    assert "does not match" in response.text


def test_approved_deploy_request_still_blocked_by_safe_v1_runner(client):
    payload = _base_payload(command="Deploy the Greek yogurt website live.")
    initial = client.post("/api/runs", json=payload)
    approval = initial.json()["approval_requests"][0]
    client.post(f"/api/approvals/{approval['id']}/decision", json={"decision": "approved"})

    payload["approval_ids"] = [approval["id"]]
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 403
    assert "not implemented" in response.text


def test_pending_approvals_endpoint_lists_pending_items(client):
    client.post("/api/runs", json=_base_payload(command="Use GPT-5.5 as CEO and continue the Greek yogurt website."))
    pending = client.get("/api/approvals/pending")
    assert pending.status_code == 200
    assert any(item["approval_type"] == "expensive_ceo_model" for item in pending.json())
