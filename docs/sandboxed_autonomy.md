# Sandboxed Autonomy v1

Sandboxed Autonomy v1 lets TheHiveMind do real local work without giving agents unrestricted computer control.

Agents can now create files inside an isolated per-run workspace, run safe validation commands, save generated files as artifacts, and update memory with summaries. Mock mode remains the default and no live LLM calls are required for the deterministic prototype build.

## What Agents Can Do

- Create safe text/code files inside `backend/data/workspaces/{run_id}/`.
- Edit files inside that run workspace.
- Run allowlisted validation commands.
- Use task packets with only task-specific context.
- Use previous artifacts as handoff inputs.
- Register generated files, manifests, and command logs as artifacts.

## What Agents Cannot Do

- Touch `.env` or secret files.
- Read/write outside the run workspace through workspace APIs.
- Delete the repo.
- Install packages.
- Push to GitHub or reset Git state.
- Send emails or post to social media.
- Deploy to production.
- Run arbitrary shell commands.
- Use web search or grounding in this step.

## First Supported Build

`run_type="prototype_build"` supports:

```text
Create a simple Greek yogurt order website prototype with files.
```

It creates a standard-library Python/HTML prototype and validates `app.py` with:

```text
python -m py_compile generated/greek_yogurt_site/app.py
```

The prototype server is not started automatically.

## Why This Is Safer Than Full Computer Control

The system uses explicit allowlists for file extensions, blocked path patterns, and command prefixes. Every file write is logged in `manifest.json`; every command result is logged in `logs/commands.json`; and generated outputs are exposed through artifact APIs for review.
