# Inter-Agent Handoff

Sandboxed Autonomy v1 avoids free-form agent chatter. Agents communicate through task packets, artifact summaries, selected artifact IDs, and the workspace manifest.

## Task Packet

Each agent receives:

- `run_id`
- `task_id`
- `agent_name`
- `agent_role`
- `objective`
- `relevant_memory`
- `input_artifacts`
- `expected_outputs`
- `constraints`
- `allowed_tools`

This prevents every worker from receiving the full run history or all memory.

## Prototype Build Handoff

```text
CEO Agent -> ceo_plan.md
Model Selector Agent -> model_selection.json
Operations Agent -> operations_checklist.md
Content Agent -> content_calendar.md
File Builder Agent -> workspace files
Safe Command Runner -> logs/commands.json
QA Agent -> qa_review.md
TheHiveMind -> final_report.md
```

The File Builder Agent receives the CEO, operations, and content artifact IDs as inputs, then creates files inside the sandbox workspace. QA receives artifact summaries and command results rather than unrestricted filesystem access.

## Why This Pattern

Artifact-based handoff makes each agent boundary visible. It also gives the UI and API a stable way to show what was produced, edited, validated, and reviewed.
