# Run Vs Project Workspace

The project folder answers:

```text
What exists in the project now?
```

The run folder answers:

```text
What happened during this run?
```

Project workspace:

```text
backend/data/projects/{project_id}/
```

Run log workspace:

```text
backend/data/runs/{run_id}/
```

Each run folder can contain:

```text
run_summary.json
timeline.json
artifacts/
workspace_snapshot.json
file_changes.json
commands.json
```

The project folder is persistent. Run 1 can create `website/app.py`; Run 2 with the same `project_id` can read the manifest and update that same file. It should not create a duplicate `generated/greek_yogurt_site_2/` folder.

Artifacts still belong to a run. When a run creates or edits a project file, the artifact record points to that project file and uses a type such as `project_file`, `project_manifest`, `project_state`, or `command_log`.

This separation keeps auditability without scattering the real work across disconnected run directories.
