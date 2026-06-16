# Usage Tracking

TheHiveMind tracks AI usage internally before relying on provider billing APIs. Internal tracking gives the dashboard fast, run-level observability for model choices, token usage, cost estimates, latency, failures, cache savings, and budget health.

## Internal Tracking vs Provider Billing

Internal tracking is written whenever TheHiveMind calls a provider through the guarded provider router. It records sanitized metadata only and never stores API keys or prompt text by default.

Provider billing sync is not implemented yet. Placeholder functions exist in `backend/app/analytics/provider_billing.py` and return:

```json
{
  "supported": false,
  "message": "Official provider billing sync is not implemented yet. Internal tracking is active."
}
```

## Tracked Metrics

Usage logs include:

- provider, model, mode, request type
- run, task, agent name, and agent role when available
- input, output, cached, and reasoning tokens
- search calls and search cost placeholders
- input, output, cached, estimated, total, and actual cost fields
- latency, success/failure, short error message, and safe metadata

## Cost Estimation

Costs are estimated from `backend/app/core/model_registry.py`. If a provider returns actual cost, such as possible OpenRouter responses, `actual_cost_usd` can be stored separately. Analytics use effective cost:

- actual cost when available
- otherwise estimated or total internal cost

## Budget Status

Budget settings live in `.env`:

```env
MONTHLY_AI_BUDGET_USD=10.00
DAILY_AI_BUDGET_USD=1.00
WARNING_BUDGET_PERCENT=70
DANGER_BUDGET_PERCENT=90
```

Budget states:

- `safe`: below warning percent
- `warning`: at or above warning percent
- `danger`: at or above danger percent
- `exceeded`: at or above 100 percent

## Demo Data

Seed realistic mock analytics data in development:

```bash
curl -X POST http://127.0.0.1:8000/api/usage/seed-demo
```

This inserts mock rows for OpenAI, Gemini, and OpenRouter models without making paid calls.

## CSV Export

Export safe usage columns:

```bash
curl "http://127.0.0.1:8000/api/usage/export.csv?range=30d"
```

The CSV excludes prompts, raw secrets, and API keys.

## Analytics Endpoints

- `GET /api/usage/summary?range=30d`
- `GET /api/usage/providers?range=30d`
- `GET /api/usage/models?range=30d`
- `GET /api/usage/agents?range=30d`
- `GET /api/usage/tokens?range=30d`
- `GET /api/usage/latency?range=30d`
- `GET /api/usage/failures?range=30d`
- `GET /api/usage/recent?limit=20`
- `GET /api/usage/expensive-runs?limit=10`
- `GET /api/usage/budget?range=30d`
- `GET /api/usage/search?range=30d`
- `GET /api/usage/cache?range=30d`
- `GET /api/usage/timeseries?range=30d&bucket=day`
- `GET /api/usage/export.csv?range=30d`
- `POST /api/usage/seed-demo`

Supported ranges: `today`, `7d`, `30d`, `month`, `all`.

Supported timeseries buckets: `hour`, `day`, `week`.

## Limitations

- Provider billing sync is not implemented.
- Search and grounding are disabled, but fields are ready.
- Token counts may be estimated if a provider does not return exact usage.
- The full multi-agent run path remains mock by default.
