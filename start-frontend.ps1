$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot 'frontend')
try {
    & npm.cmd run start -- --hostname 127.0.0.1
} finally {
    Pop-Location
}
