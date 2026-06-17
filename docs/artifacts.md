# Artifacts

Run Engine v1 saves local artifacts for every controlled run.

## Location

Artifacts are written to:

```text
backend/data/artifacts/{run_id}/
```

`backend/data/` is ignored by Git so generated outputs are not committed.

## Artifact Types

Each run creates:

- `ceo_plan.md`
- `model_selection.json`
- `research_brief.md`
- `content_calendar.md`
- `operations_checklist.md`
- `qa_review.md`
- `final_report.md`
- `run_summary.json`

Each artifact has metadata:

- `id`
- `run_id`
- `name`
- `type`
- `path`
- `created_at`
- `agent_name`
- `summary`

## Endpoints

```http
GET /api/runs/{run_id}/artifacts
GET /api/runs/{run_id}/artifacts/{artifact_id}
```

The list endpoint returns metadata. The detail endpoint returns metadata plus `content`.

## Design Notes

Artifacts are plain local files for v1. This keeps the system transparent and easy to inspect. A later version can move artifact metadata into a database table and add file versioning, project folders, approvals, and exports.
