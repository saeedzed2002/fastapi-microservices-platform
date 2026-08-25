[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("install", "lint", "format-check", "typecheck", "test", "migrate-identity", "migrate-customer", "dev-up", "dev-down", "logs")]
    [string]$Task
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$uvPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
$composeFile = Join-Path $repoRoot "infrastructure\compose\docker-compose.yml"

if (-not (Test-Path $uvPath)) {
    throw "uv was not found at $uvPath. Install the verified version documented in docs/development/toolchain.md."
}

Push-Location $repoRoot
try {
    switch ($Task) {
        "install" { & $uvPath sync --locked --all-packages }
        "lint" { & $uvPath run --all-packages ruff check . }
        "format-check" { & $uvPath run --all-packages ruff format --check . }
        "typecheck" { & $uvPath run --all-packages mypy }
        "test" { & $uvPath run --all-packages pytest }
        "migrate-identity" { & $uvPath run --package identity-service alembic -c services/identity-service/alembic.ini upgrade head }
        "migrate-customer" { & $uvPath run --package customer-service alembic -c services/customer-service/alembic.ini upgrade head }
        "dev-up" { docker compose -f $composeFile up -d --build }
        "dev-down" { docker compose -f $composeFile down }
        "logs" { docker compose -f $composeFile logs -f }
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
