# Official Provider Usage Sync

TheHiveMind separates usage into four buckets:

- `provider_response`: usage metadata returned by a live provider response, such as token counts or response IDs.
- `provider_generation_lookup`: provider usage fetched after a live call using a generation/request ID, currently used for OpenRouter.
- `provider_official_billing`: official provider usage or cost data fetched from provider admin APIs or billing export.
- `provider_account_balance`: account-wide credit/balance data, such as OpenRouter `/credits`.
- `mock_dev_only` and `safety_estimate_dev_only`: development-only estimates, hidden from real dashboard totals by default.

Mock mode never spends model credits. Mock costs are simulated live-equivalent estimates so model routing can be inspected before any live call is approved.

## Approval Gates

Official usage sync is read-only and does not require an approval card. It does not make model calls, does not enable live mode, and does not bypass approval gates. Live mode, GPT-5.5 CEO use, deploys, package installs, payments, external actions, and dangerous commands still go through the approval gate and backend safety controls.

## OpenAI

OpenAI official sync uses `OPENAI_ADMIN_API_KEY`, not the normal model key. It calls the organization costs and completions usage endpoints defensively, stores raw provider responses with sensitive fields redacted, and normalizes buckets into `ProviderUsageRecord` rows.

```env
OPENAI_ADMIN_API_KEY=...
ENABLE_OPENAI_OFFICIAL_USAGE_SYNC=true
```

If the admin key is missing or unauthorized, the app reports that official OpenAI sync is unavailable and continues running normally.

## OpenRouter

OpenRouter official sync uses `OPENROUTER_MANAGEMENT_KEY` against the credits endpoint. It stores total credits, total usage, remaining credits, and the raw response as `provider_account_balance` with account scope. This is not counted as TheHiveMind run-level spend. Live OpenRouter calls store provider response usage and, when a generation ID is available, fetch generation metadata as `provider_generation_lookup`.

```env
OPENROUTER_MANAGEMENT_KEY=...
ENABLE_OPENROUTER_OFFICIAL_USAGE_SYNC=true
```

## Google / Gemini

Gemini live calls store provider-response usage metadata when returned by the SDK, including prompt, cached, candidate, thoughts, total token counts, model version, and response ID where available.

Official Google usage comes from Cloud Billing export in BigQuery:

```env
GOOGLE_CLOUD_PROJECT_ID=thehivemind-billing
GOOGLE_BILLING_BIGQUERY_DATASET=billing_export
GOOGLE_BILLING_LOCATION=US
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\Ahmed\secure\gcp-billing-reader.json
ENABLE_GOOGLE_BILLING_SYNC=true
```

Billing export tables can take hours, and sometimes days for backfill, to appear. If the dataset exists but no export tables are visible yet, TheHiveMind reports `waiting_for_tables` instead of crashing.

## API

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/official-usage/status
Invoke-RestMethod http://127.0.0.1:8000/api/official-usage/summary
Invoke-RestMethod http://127.0.0.1:8000/api/official-usage/reconciliation
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/official-usage/sync
```

Additional provider-specific endpoints:

- `GET /api/official-usage/openai?range=30d`
- `GET /api/official-usage/openrouter?range=30d`
- `GET /api/official-usage/google?range=30d`
- `GET /api/official-usage/raw/{provider}?limit=20`

Responses never include API keys or service account JSON.

## Reconciliation

Reconciliation compares local usage logs with official records:

- `mock_only`: no live calls and no official records.
- `estimated`: live local logs exist, but official data is missing or delayed.
- `provider_reported`: official provider data exists.
- `reconciled`: matching provider-given values are close, within `$0.01` or `5%`.
- `not_comparable`: the records use different scopes, such as account-wide credits versus one run.
- `unavailable`: sync is disabled, missing credentials, or provider data is not available.
- `error`: provider sync failed in a recoverable way.
