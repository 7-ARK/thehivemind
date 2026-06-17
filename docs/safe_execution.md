# Safe Execution

TheHiveMind defaults to mock mode. Run Engine v1 is designed to produce useful planning artifacts without spending money or taking external actions.

## Live Mode Gates

Live provider calls require all of the following:

- Request body sets `"mode": "live"`.
- `.env` sets `ALLOW_LIVE_CALLS=true`.
- The provider API key is configured.
- Per-call token and cost limits pass.
- Per-run cost limits pass.

## CEO Model Guard

The configured CEO model is not called automatically in live mode. If a live run does not set:

```json
{
  "allow_ceo_live": true
}
```

Run Engine v1 downgrades the CEO step to the cheap worker model.

## Disabled Actions

Run Engine v1 does not:

- send emails
- post to social media
- deploy code
- purchase services
- call search or grounding tools
- perform supplier sourcing
- execute physical production steps

## Usage Logging

Every run step writes a usage row with:

- provider
- model
- mode
- request type
- run ID and task ID
- agent name and role
- input/output/cached/reasoning tokens when available
- search calls and search cost placeholders
- estimated and actual cost fields
- latency and success/failure

The usage dashboard and `/api/usage/*` endpoints read from this internal usage log.

## Tracking ID

`OPENAI_TRACKING_ID` is available as an ignored local `.env` setting. It is not committed, printed, or sent by default. It can be included in future provider metadata if OpenAI support asks you to correlate a specific run.
