$ErrorActionPreference = 'Stop'
$backendDir = Join-Path $PSScriptRoot 'backend'
$pythonPath = Join-Path $backendDir '.venv-runtime\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Backend environment missing. Create backend/.venv-runtime and install backend/requirements.txt first.'
}
Push-Location $backendDir
try {
    & $pythonPath -m uvicorn main:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}
