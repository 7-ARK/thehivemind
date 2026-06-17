# Cost Guardrails

TheHiveMind keeps live execution behind explicit budget controls.

Per-call guards:

- `MAX_INPUT_TOKENS_PER_CALL`
- `MAX_OUTPUT_TOKENS_PER_CALL`
- `MAX_COST_PER_CALL_USD`

Per-run guards:

- Request `max_cost_usd`
- `MAX_COST_PER_RUN_USD`

Provider calls go through:

```text
backend/app/providers/provider_router.py
```

The provider router estimates tokens and cost before calling the provider. It also checks that live calls are enabled and the provider key is configured.

Every provider call logs:

- run id
- task id
- agent name and role
- provider
- model
- mode
- input and output tokens
- estimated cost
- latency
- success or failure
- sanitized metadata, including project id

Usage can be inspected through:

```text
GET /api/usage/summary
GET /api/usage/providers
GET /api/usage/models
GET /api/usage/agents
GET /api/usage/recent
```

GPT-5.5 is blocked by default in live runs unless the request explicitly sets `allow_ceo_live=true`.
