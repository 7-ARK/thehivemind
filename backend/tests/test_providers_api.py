import asyncio
import sys
from types import SimpleNamespace

import pytest


def test_api_index_and_favicon_are_intentional(client):
    index = client.get("/")
    assert index.status_code == 200
    payload = index.json()
    assert payload["name"] == "TheHiveMind API"
    assert payload["docs"] == "/docs"
    assert payload["endpoints"]["runs"] == "/api/runs"

    favicon = client.get("/favicon.ico")
    assert favicon.status_code == 204


def test_provider_status_hides_secrets(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.get("/api/providers/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"]["openai"]["configured"] is True
    assert "sk-secret-value" not in response.text
    assert "openai_api_key" not in response.text


def test_live_mode_blocked_when_not_allowed(client):
    response = client.post(
        "/api/providers/test",
        json={
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "mode": "live",
            "prompt": "Reply with one short sentence saying TheHiveMind provider test worked.",
            "max_output_tokens": 80,
        },
    )
    assert response.status_code == 403
    assert "Live provider calls are disabled" in response.text


def test_missing_api_key_gives_clear_error(client, monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.post(
        "/api/providers/test",
        json={
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "mode": "live",
            "prompt": "Reply with one short sentence.",
            "max_output_tokens": 20,
        },
    )
    assert response.status_code == 400
    assert "API key is not configured" in response.text


@pytest.mark.parametrize(
    ("provider", "model", "key_name"),
    [
        ("openai", "gpt-5.4-nano", "OPENAI_API_KEY"),
        ("gemini", "gemini-3.5-flash", "GEMINI_API_KEY"),
        ("openrouter", "qwen/qwen3-coder", "OPENROUTER_API_KEY"),
    ],
)
def test_live_provider_failures_report_sanitized_details_for_all_providers(client, monkeypatch, provider, model, key_name):
    class FakeResponse:
        status_code = 429
        text = '{"error":"quota exceeded","token":"sk-body-secret-123456789"}'

    class FakeProviderError(RuntimeError):
        status_code = 429
        code = "rate_limit_exceeded"
        response = FakeResponse()

    class FailingProvider:
        async def generate(self, **_kwargs):
            raise FakeProviderError(
                "quota exceeded with api_key=sk-test-secret-123456789 and Authorization: Bearer provider-secret-token"
            )

    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv(key_name, "configured-test-key")
    from app.core.config import get_settings
    from app.providers import provider_router

    get_settings.cache_clear()
    monkeypatch.setitem(provider_router.PROVIDERS, provider, FailingProvider)

    response = client.post(
        "/api/providers/test",
        json={
            "provider": provider,
            "model": model,
            "mode": "live",
            "prompt": "Trigger a mocked provider failure.",
            "max_output_tokens": 20,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert f"Provider call failed for {provider}/{model}" in detail
    assert "FakeProviderError" in detail
    assert "status=429" in detail
    assert "code=rate_limit_exceeded" in detail
    assert "usage_log_id=" in detail
    assert "sk-test-secret" not in detail
    assert "provider-secret-token" not in detail
    assert "sk-body-secret" not in detail
    assert "[redacted]" in detail

    usage = client.get("/api/usage/recent?limit=1")
    assert usage.status_code == 200
    recent = usage.json()["recent_calls"][0]
    assert recent["success"] is False
    assert recent["provider"] == provider
    assert recent["metadata"]["provider_error"]["provider"] == provider
    assert recent["metadata"]["provider_error"]["status_code"] == 429
    assert "sk-test-secret" not in recent["error_message"]
    assert "provider-secret-token" not in recent["metadata"]["provider_error"]["summary"]


def test_openai_gpt55_request_omits_temperature_and_forwards_json_schema(client, monkeypatch):
    captured: list[dict] = []

    class FakeResponses:
        async def create(self, **request):
            captured.append(request)
            usage = SimpleNamespace(input_tokens=10, output_tokens=5, input_tokens_details=None)
            return SimpleNamespace(id="resp-test", output_text="ok", usage=usage)

    class FakeAsyncOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    from app.core.config import get_settings
    from app.providers.openai_provider import OpenAIProvider

    get_settings.cache_clear()
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "tiny_schema",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["answer"],
                "properties": {"answer": {"type": "string"}},
            },
        },
    }
    asyncio.run(
        OpenAIProvider().generate(
            model="gpt-5.5",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.2,
            response_format=response_format,
        )
    )

    assert captured
    assert captured[0]["model"] == "gpt-5.5"
    assert "temperature" not in captured[0]
    assert captured[0]["text"]["format"]["type"] == "json_schema"
    assert captured[0]["text"]["format"]["name"] == "tiny_schema"
    assert captured[0]["text"]["format"]["strict"] is True


def test_openai_non_gpt55_request_keeps_temperature(client, monkeypatch):
    captured: list[dict] = []

    class FakeResponses:
        async def create(self, **request):
            captured.append(request)
            usage = SimpleNamespace(input_tokens=10, output_tokens=5, input_tokens_details=None)
            return SimpleNamespace(id="resp-test", output_text="ok", usage=usage)

    class FakeAsyncOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    from app.core.config import get_settings
    from app.providers.openai_provider import OpenAIProvider

    get_settings.cache_clear()
    asyncio.run(OpenAIProvider().generate(model="gpt-5.4-nano", messages=[{"role": "user", "content": "hi"}], temperature=0.2))

    assert captured
    assert captured[0]["model"] == "gpt-5.4-nano"
    assert captured[0]["temperature"] == 0.2


def test_openai_json_object_response_format_uses_responses_text_format(client, monkeypatch):
    captured: list[dict] = []

    class FakeResponses:
        async def create(self, **request):
            captured.append(request)
            usage = SimpleNamespace(input_tokens=10, output_tokens=5, input_tokens_details=None)
            return SimpleNamespace(id="resp-test", output=[{"content": [{"text": "{\"answer\":\"ok\"}"}]}], usage=usage)

    class FakeAsyncOpenAI:
        def __init__(self, api_key):
            self.api_key = api_key
            self.responses = FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    from app.core.config import get_settings
    from app.providers.openai_provider import OpenAIProvider

    get_settings.cache_clear()
    response = asyncio.run(
        OpenAIProvider().generate(
            model="gpt-5.4-nano",
            messages=[{"role": "user", "content": "hi"}],
            response_format={"type": "json_object"},
        )
    )

    assert captured[0]["text"] == {"format": {"type": "json_object"}}
    assert response.text == "{\"answer\":\"ok\"}"
    assert response.raw_metadata["requested_response_format"] == {"type": "json_object"}


def test_business_builder_live_planning_has_dedicated_output_cap(client, monkeypatch):
    class CapturingProvider:
        async def generate(self, **kwargs):
            from app.providers.base_provider import ProviderResponse

            return ProviderResponse(
                provider="openai",
                model=kwargs["model"],
                text="{\"ok\":true}",
                input_tokens=10,
                output_tokens=5,
                estimated_cost_usd=0.001,
                latency_ms=1,
            )

    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    from app.core.config import get_settings
    from app.providers import provider_router

    get_settings.cache_clear()
    monkeypatch.setitem(provider_router.PROVIDERS, "openai", CapturingProvider)

    response, usage_id = asyncio.run(
        provider_router.generate_with_provider(
            provider="openai",
            model="gpt-5.5",
            mode="live",
            messages=[{"role": "user", "content": "hi"}],
            max_output_tokens=1200,
            request_type="business_builder_live_planning",
        )
    )

    assert response.text == "{\"ok\":true}"
    assert usage_id


def test_regular_provider_test_still_uses_default_output_cap(client, monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    from app.core.config import get_settings
    from app.providers import provider_router

    get_settings.cache_clear()
    with pytest.raises(Exception, match="max_output_tokens exceeds configured output token limit=500"):
        asyncio.run(
            provider_router.generate_with_provider(
                provider="openai",
                model="gpt-5.5",
                mode="live",
                messages=[{"role": "user", "content": "hi"}],
                max_output_tokens=1200,
                request_type="provider_test",
            )
        )


def test_mock_provider_test_writes_usage_log(client):
    response = client.post(
        "/api/providers/test",
        json={
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "mode": "mock",
            "prompt": "Reply with one short sentence saying TheHiveMind provider test worked.",
            "max_output_tokens": 80,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["provider"] == "mock"
    assert payload["usage_log_id"]
    assert payload["estimated_cost_usd"] >= 0

    summary = client.get("/api/usage/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["total_input_tokens"] > 0
    assert summary_payload["calls_by_provider"]["mock"] == 1
    assert len(summary_payload["recent_calls"]) == 1


def test_usage_summary_empty_shape(client):
    response = client.get("/api/usage/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_estimated_cost_usd"] == 0
    assert payload["calls_by_provider"] == {}
    assert payload["recent_calls"] == []


def test_existing_mock_run_still_works(client):
    response = client.post("/api/runs", json={"command": "Plan a safe launch", "mode": "mock"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert len(payload["events"]) == 7

    usage = client.get("/api/usage/summary?range=all")
    assert usage.status_code == 200
    usage_payload = usage.json()
    assert usage_payload["total_calls"] == 7
    assert usage_payload["calls_by_provider"]["openai"] >= 1
    assert usage_payload["calls_by_provider"]["gemini"] >= 1

    expensive_runs = client.get("/api/usage/expensive-runs?limit=1")
    assert expensive_runs.status_code == 200
    run_payload = expensive_runs.json()["runs"][0]
    assert run_payload["run_id"] == payload["run_id"]
    assert run_payload["title"] == "Plan a safe launch"
