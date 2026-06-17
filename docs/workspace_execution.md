# Workspace Execution

Each autonomous run gets an isolated workspace:

```text
backend/data/workspaces/{run_id}/
```

The workspace contains:

```text
generated/
logs/commands.json
manifest.json
```

## File Safety

Allowed extensions:

```text
.py .ts .tsx .js .jsx .json .md .txt .html .css .yml .yaml .toml
```

Blocked paths and patterns include:

```text
.env
*.env
.git/
node_modules/
.venv/
__pycache__/
dist/
build/
.next/
backend/data/secrets/
```

All paths are resolved against the run workspace. Absolute paths and `../` traversal are rejected.

## Command Safety

Allowed command prefixes:

```text
python --version
python -m py_compile
python -m pytest
pytest
npm run build
npm run lint
npm test
```

Blocked examples:

```text
rm
del
rmdir
format
curl
wget
ssh
scp
git push
git reset
pip install
npm install
docker
powershell
```

Commands run with `shell=False`, inside the workspace, with stdout/stderr/exit code/duration captured. The default timeout is 30 seconds.

## Workspace APIs

```http
GET /api/runs/{run_id}/workspace/files
GET /api/runs/{run_id}/workspace/files/{path}
GET /api/runs/{run_id}/workspace/manifest
GET /api/runs/{run_id}/workspace/commands
```

Workspace file reads use the same safety policy and never expose `.env`.
