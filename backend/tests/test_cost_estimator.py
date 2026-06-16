from fastapi import HTTPException

from app.core.cost_estimator import assert_call_budget, estimate_cost, estimate_tokens


def test_cost_estimator_uses_registry_prices():
    estimate = estimate_cost("gpt-5.4-nano", input_tokens=1000, output_tokens=100)
    assert estimate.estimated_cost_usd == 0.000325
    assert estimate.input_tokens == 1000
    assert estimate.output_tokens == 100


def test_token_estimator_is_small_and_stable():
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_call_budget_rejects_large_output(client):
    try:
        assert_call_budget("gpt-5.4-nano", input_tokens=100, output_tokens=9999)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "MAX_OUTPUT_TOKENS_PER_CALL" in exc.detail
    else:
        raise AssertionError("Expected budget guard to reject oversized output")
