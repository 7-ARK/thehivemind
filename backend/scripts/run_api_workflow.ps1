Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "Starting TheHiveMind API for workflow testing without reload..."
Write-Host "Use this mode before live/mock agent workflow testing so backend/data writes do not restart Uvicorn."

.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
