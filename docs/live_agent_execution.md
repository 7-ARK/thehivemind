# Live Agent Execution v1

Live Agent Execution v1 lets TheHiveMind run the same controlled workflow through configured provider adapters while keeping mock mode as the default.

Live mode is guarded by all of these:

- Request body must use `"mode": "live"`
- `.env` must set `ALLOW_LIVE_CALLS=true`
- The provider key must exist
- Token limits must pass
- Cost limits must pass
- The selected model must be routed through the approved model registry
- GPT-5.5 is not used unless `allow_ceo_live=true`

When `allow_ceo_live=false`, the CEO step uses `CEO_FALLBACK_MODEL`, defaulting to `gpt-5.4-nano`.

The common live runner is:

```text
backend/app/agents/llm_agent_runner.py
```

Every agent receives an `AgentExecutionContext`, not the whole project. It includes the run id, project id, command, objective, relevant memory, relevant project file summaries, input artifact summaries, constraints, allowed tools, model, provider, and budget.

The File Builder Agent can request structured file actions:

```json
{
  "file_actions": [
    {
      "operation": "create",
      "path": "website/app.py",
      "summary": "Simple prototype backend",
      "content": "..."
    }
  ]
}
```

The backend validates all file paths and extensions before writing. Invalid JSON falls back to the deterministic safe builder and is mentioned in the run timeline.

No live tests make paid calls. Tests patch the common runner and verify guards, fallback CEO behavior, usage logs, invalid file actions, and cost limits.
