# Continuation Flow

Persistent Project Workspace v1 lets follow-up runs continue from existing work.

Run 1:

```text
Create a simple Greek yogurt order website prototype with files.
```

Creates:

```text
backend/data/projects/greek-yogurt-test/website/app.py
backend/data/projects/greek-yogurt-test/website/templates/index.html
backend/data/projects/greek-yogurt-test/website/data/sample_orders.json
```

Run 2:

```text
Continue the Greek yogurt website and add a simple order status page.
```

Reads:

- `project_state.md`
- `manifest.json`
- relevant `website/` file summaries
- relevant memory summaries

Then updates existing files:

```text
website/app.py
website/templates/index.html
```

And adds new files:

```text
website/templates/status.html
website/data/order_statuses.json
```

Agents receive task packets with only relevant project context:

- project id
- project state summary
- manifest summaries for relevant files
- previous artifact ids needed for handoff
- expected outputs
- constraints
- allowed tools

This avoids loading every artifact and every file into every worker prompt. Memory stores project updates, file changes, agent decisions, and run summaries as compact summaries with metadata.
