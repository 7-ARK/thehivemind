Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "Starting TheHiveMind API for backend code development with reload..."
Write-Host "Reload is scoped to app/ to avoid backend/data project file writes restarting the server."

.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --port 8000
