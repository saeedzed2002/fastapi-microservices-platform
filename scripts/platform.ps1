[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("install", "lint", "format-check", "typecheck", "test", "migrate-identity", "migrate-customer", "migrate-catalog", "migrate-media", "migrate-inventory", "migrate-cart", "migrate-order", "migrate-payment", "migrate-notification", "migrate-chat", "provision-admin", "dev-up", "dev-start", "dev-stop", "dev-recreate", "dev-down", "logs")]
    [string]$Task,
    [string]$AdminEmail
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$uvPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
$composeFile = Join-Path $repoRoot "infrastructure\compose\docker-compose.yml"
$composeEnvironmentFile = Join-Path $repoRoot ".env"
$composeArguments = @("-f", $composeFile)

if (Test-Path -LiteralPath $composeEnvironmentFile) {
    $composeArguments = @("--env-file", $composeEnvironmentFile) + $composeArguments
}

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
        "migrate-catalog" { & $uvPath run --package catalog-service alembic -c services/catalog-service/alembic.ini upgrade head }
        "migrate-media" { & $uvPath run --package media-service alembic -c services/media-service/alembic.ini upgrade head }
        "migrate-inventory" { & $uvPath run --package inventory-service alembic -c services/inventory-service/alembic.ini upgrade head }
        "migrate-cart" { & $uvPath run --package cart-service alembic -c services/cart-service/alembic.ini upgrade head }
        "migrate-order" { & $uvPath run --package order-service alembic -c services/order-service/alembic.ini upgrade head }
        "migrate-payment" { & $uvPath run --package payment-service alembic -c services/payment-service/alembic.ini upgrade head }
        "migrate-notification" { & $uvPath run --package notification-service alembic -c services/notification-service/alembic.ini upgrade head }
        "migrate-chat" { & $uvPath run --package chat-service alembic -c services/chat-service/alembic.ini upgrade head }
        "provision-admin" {
            if ([string]::IsNullOrWhiteSpace($AdminEmail)) {
                throw "-AdminEmail is required for provision-admin."
            }
            & $uvPath run --package identity-service python -m identity_service.admin_provision --email $AdminEmail
        }
        "dev-up" {
            & docker compose @composeArguments build
            & docker compose @composeArguments up -d
        }
        "dev-start" { & docker compose @composeArguments start }
        "dev-stop" { & docker compose @composeArguments stop }
        "dev-recreate" { & docker compose @composeArguments up -d --force-recreate }
        "dev-down" { & docker compose @composeArguments down }
        "logs" { & docker compose @composeArguments logs -f }
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
