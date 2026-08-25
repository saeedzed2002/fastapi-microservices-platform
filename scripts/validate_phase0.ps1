$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($PSVersionTable.PSVersion -lt [version]"7.4") {
    [Console]::Error.WriteLine("Phase 0 validation requires PowerShell 7.4 or later for Draft 2020-12 JSON Schema validation. Run it with a compatible pwsh.")
    exit 1
}
$testJsonCommand = Get-Command Test-Json -ErrorAction SilentlyContinue
if ($null -eq $testJsonCommand -or "SchemaFile" -notin $testJsonCommand.Parameters.Keys) {
    [Console]::Error.WriteLine("Phase 0 validation requires Test-Json with the SchemaFile parameter.")
    exit 1
}

$repositoryPath = Split-Path -Parent $PSScriptRoot
$validationErrors = [System.Collections.Generic.List[string]]::new()

function Add-ValidationError {
    param([Parameter(Mandatory)][string]$Message)
    $validationErrors.Add($Message)
}

function Test-JsonSchemaDocument {
    param(
        [Parameter(Mandatory)][string]$DocumentPath,
        [Parameter(Mandatory)][string]$SchemaPath,
        [Parameter(Mandatory)][string]$Label
    )

    try {
        $schemaErrors = @()
        $document = Get-Content -LiteralPath $DocumentPath -Raw
        $isValid = $document | Test-Json -SchemaFile $SchemaPath -ErrorAction SilentlyContinue -ErrorVariable schemaErrors
        if (-not $isValid) {
            $detail = if ($schemaErrors.Count -gt 0) {
                $schemaErrors[0].Exception.Message
            }
            else {
                "schema validation returned false"
            }
            Add-ValidationError "Invalid ${Label}: $DocumentPath against ${SchemaPath}: $detail"
        }
    }
    catch {
        Add-ValidationError "Unable to validate ${Label}: $($_.Exception.Message)"
    }
}

function Test-CanonicalUuid {
    param([AllowNull()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    $parsedGuid = [guid]::Empty
    return [guid]::TryParseExact($Value, "D", [ref]$parsedGuid)
}

function Test-UtcTimestamp {
    param([AllowNull()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    if ($Value -notmatch '^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T([01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?Z$') {
        return $false
    }
    $parsedTimestamp = [DateTimeOffset]::MinValue
    $dateTimeStyles = [Globalization.DateTimeStyles]::RoundtripKind
    if ([DateTimeOffset]::TryParseExact(
        $Value,
        "yyyy-MM-dd'T'HH:mm:ssK",
        [Globalization.CultureInfo]::InvariantCulture,
        $dateTimeStyles,
        [ref]$parsedTimestamp
    )) {
        return $true
    }
    return [DateTimeOffset]::TryParseExact(
        $Value,
        "yyyy-MM-dd'T'HH:mm:ss.FFFFFFFK",
        [Globalization.CultureInfo]::InvariantCulture,
        $dateTimeStyles,
        [ref]$parsedTimestamp
    )
}

$repositoryFiles = @(Get-ChildItem -LiteralPath $repositoryPath -Recurse -File -Force | Where-Object {
    $_.FullName -notmatch '[\\/]\.(git|venv)[\\/]'
})
$jsonFiles = @($repositoryFiles | Where-Object { $_.Extension -eq ".json" })
$markdownFiles = @($repositoryFiles | Where-Object { $_.Extension -eq ".md" })
$textFiles = @($repositoryFiles | Where-Object {
    $_.Extension -in @(".md", ".json", ".yml", ".yaml", ".ps1", ".toml") -or $_.Name -in @(".editorconfig", ".gitattributes", ".gitignore")
})

foreach ($jsonFile in $jsonFiles) {
    try {
        $null = Get-Content -LiteralPath $jsonFile.FullName -Raw | ConvertFrom-Json -Depth 100
    }
    catch {
        Add-ValidationError "Invalid JSON: $($jsonFile.FullName): $($_.Exception.Message)"
    }
}

Test-JsonSchemaDocument -DocumentPath (Join-Path $repositoryPath "contracts/catalog.json") -SchemaPath (Join-Path $repositoryPath "contracts/catalog.schema.json") -Label "contract catalog"
Test-JsonSchemaDocument -DocumentPath (Join-Path $repositoryPath "contracts/events/event-envelope.v1.example.json") -SchemaPath (Join-Path $repositoryPath "contracts/events/event-envelope.v1.schema.json") -Label "event-envelope example"
Test-JsonSchemaDocument -DocumentPath (Join-Path $repositoryPath "contracts/openapi/error-response.v1.example.json") -SchemaPath (Join-Path $repositoryPath "contracts/openapi/error-response.v1.schema.json") -Label "error-response example"

foreach ($markdownFile in $markdownFiles) {
    $markdown = Get-Content -LiteralPath $markdownFile.FullName -Raw
    $fenceCount = ([regex]::Matches($markdown, '(?m)^```')).Count
    if (($fenceCount % 2) -ne 0) {
        Add-ValidationError "Unbalanced Markdown code fences: $($markdownFile.FullName)"
    }

    foreach ($linkMatch in [regex]::Matches($markdown, "\[[^\]]+\]\(([^)]+)\)")) {
        $target = $linkMatch.Groups[1].Value.Trim()
        if ($target.StartsWith("<") -and $target.EndsWith(">")) {
            $target = $target.Substring(1, $target.Length - 2)
        }
        if ($target -match "^(https?://|mailto:|#)") {
            continue
        }

        $pathPart = ($target -split "#", 2)[0]
        if ([string]::IsNullOrWhiteSpace($pathPart)) {
            continue
        }

        $resolvedPath = [System.IO.Path]::GetFullPath((Join-Path $markdownFile.DirectoryName $pathPart))
        if (-not (Test-Path -LiteralPath $resolvedPath)) {
            Add-ValidationError "Broken local link: $($markdownFile.FullName) -> $target"
        }
    }
}

foreach ($textFile in $textFiles) {
    $text = Get-Content -LiteralPath $textFile.FullName -Raw
    if ([regex]::IsMatch($text, "(?m)[ \t]+$")) {
        Add-ValidationError "Trailing whitespace: $($textFile.FullName)"
    }
}

$adrPath = Join-Path $repositoryPath "docs/adr"
$adrFiles = @(Get-ChildItem -LiteralPath $adrPath -File -Filter "ADR-*.md")
foreach ($adrFile in $adrFiles) {
    $adr = Get-Content -LiteralPath $adrFile.FullName -Raw
    foreach ($requiredHeading in @(
        "## Context",
        "## Decision",
        "## Consequences",
        "## Alternatives considered",
        "## Compatibility and migration",
        "## Validation",
        "## Related material"
    )) {
        if ($adr -notmatch "(?m)^$([regex]::Escape($requiredHeading))\s*$") {
            Add-ValidationError "ADR is missing required section '$requiredHeading': $($adrFile.FullName)"
        }
    }
}

$catalogPath = Join-Path $repositoryPath "contracts/catalog.json"
$catalog = Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json -Depth 100
$allowedKinds = @("event-envelope", "api-error-envelope", "domain-event")
$allowedStatuses = @("reserved", "proposed", "active", "deprecated", "retired")

if ($catalog.catalog_schema -ne "catalog.schema.json") {
    Add-ValidationError "Contract catalog does not identify catalog.schema.json."
}
if ($catalog.catalog_version -ne 1) {
    Add-ValidationError "Contract catalog version must be 1."
}
if ($catalog.project -ne "FastAPI Microservices Platform" -or $catalog.namespace -ne "fastapi-platform") {
    Add-ValidationError "Contract catalog project identity or namespace is invalid."
}

foreach ($duplicate in @($catalog.contracts | Group-Object name | Where-Object Count -gt 1)) {
    Add-ValidationError "Duplicate contract name: $($duplicate.Name)"
}

foreach ($contract in $catalog.contracts) {
    if ([string]::IsNullOrWhiteSpace($contract.name) -or [string]::IsNullOrWhiteSpace($contract.owner)) {
        Add-ValidationError "Contract name and owner must be non-empty."
    }
    if ($contract.kind -notin $allowedKinds) {
        Add-ValidationError "Invalid contract kind for $($contract.name): $($contract.kind)"
    }
    if ($contract.status -notin $allowedStatuses) {
        Add-ValidationError "Invalid contract status for $($contract.name): $($contract.status)"
    }
    if ($contract.status -eq "active") {
        if ([string]::IsNullOrWhiteSpace($contract.schema)) {
            Add-ValidationError "Active contract has no schema: $($contract.name)"
        }
        else {
            $activeSchemaPath = Join-Path (Join-Path $repositoryPath "contracts") $contract.schema
            if (-not (Test-Path -LiteralPath $activeSchemaPath)) {
                Add-ValidationError "Active contract schema is missing: $($contract.name) -> $($contract.schema)"
            }
        }
    }
    if ($contract.kind -eq "domain-event") {
        if ($null -eq $contract.consumers) {
            Add-ValidationError "Domain event has no consumers array: $($contract.name)"
        }
        if ($contract.name -notmatch "^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*\.v[1-9][0-9]*$") {
            Add-ValidationError "Invalid versioned event name: $($contract.name)"
        }
        if ($null -ne $contract.topic -and $contract.topic -notmatch "^fastapi-platform\.") {
            Add-ValidationError "Event topic is outside the fastapi-platform namespace: $($contract.name)"
        }
        if ($contract.status -eq "reserved" -and $null -ne $contract.schema) {
            Add-ValidationError "Reserved event must not expose an active payload schema: $($contract.name)"
        }
    }
}

$eventSchemaPath = Join-Path $repositoryPath "contracts/events/event-envelope.v1.schema.json"
$eventSchema = Get-Content -LiteralPath $eventSchemaPath -Raw | ConvertFrom-Json -Depth 100
$requiredEventFields = @(
    "event_id", "event_type", "event_version", "aggregate_type", "aggregate_id",
    "producer", "occurred_at", "correlation_id", "causation_id", "trace_id", "payload"
)
foreach ($requiredField in $requiredEventFields) {
    if ($requiredField -notin $eventSchema.required) {
        Add-ValidationError "Event envelope is missing required field: $requiredField"
    }
}
if ($eventSchema.additionalProperties -ne $true) {
    Add-ValidationError "Event envelope must allow unknown optional fields for compatible additive evolution."
}

$eventExamplePath = Join-Path $repositoryPath "contracts/events/event-envelope.v1.example.json"
$eventExampleRaw = Get-Content -LiteralPath $eventExamplePath -Raw
$eventExample = $eventExampleRaw | ConvertFrom-Json -Depth 100
if (-not (Test-CanonicalUuid $eventExample.event_id)) {
    Add-ValidationError "Event example event_id is not a canonical UUID."
}
if (-not (Test-CanonicalUuid $eventExample.aggregate_id)) {
    Add-ValidationError "Event example aggregate_id is not a canonical UUID."
}
if ($eventExample.event_type -notmatch "\.v([1-9][0-9]*)$" -or [int]$Matches[1] -ne [int]$eventExample.event_version) {
    Add-ValidationError "Event example version does not match its event_type suffix."
}
$occurredAtMatch = [regex]::Match($eventExampleRaw, '"occurred_at"\s*:\s*"([^"]+)"')
if (-not $occurredAtMatch.Success -or -not (Test-UtcTimestamp $occurredAtMatch.Groups[1].Value)) {
    Add-ValidationError "Event example occurred_at is not a valid UTC RFC 3339 timestamp."
}
if ($eventExample.trace_id -notmatch "^[0-9a-f]{32}$") {
    Add-ValidationError "Event example trace_id is not 32 lowercase hexadecimal characters."
}

$errorSchemaPath = Join-Path $repositoryPath "contracts/openapi/error-response.v1.schema.json"
$errorSchema = Get-Content -LiteralPath $errorSchemaPath -Raw | ConvertFrom-Json -Depth 100
if ("error" -notin $errorSchema.required) {
    Add-ValidationError "Error response schema does not require the error object."
}
foreach ($requiredField in @("code", "message", "details", "request_id")) {
    if ($requiredField -notin $errorSchema.properties.error.required) {
        Add-ValidationError "Error response is missing required field: $requiredField"
    }
}
$errorExamplePath = Join-Path $repositoryPath "contracts/openapi/error-response.v1.example.json"
$errorExample = Get-Content -LiteralPath $errorExamplePath -Raw | ConvertFrom-Json -Depth 100
if ($errorExample.error.request_id -notmatch "^[A-Za-z0-9._:-]{1,128}$") {
    Add-ValidationError "Error example request_id is not transport-safe."
}
if ((Test-CanonicalUuid "not-a-uuid") -or (Test-UtcTimestamp "not-a-dateZ")) {
    Add-ValidationError "Validator format self-test unexpectedly accepted invalid identifiers or timestamps."
}

$workflowPath = Join-Path $repositoryPath ".github/workflows/platform-ci.yml"
$workflow = Get-Content -LiteralPath $workflowPath -Raw
if ($workflow -notmatch "(?m)^\s*uses:\s*actions/checkout@[0-9a-f]{40}\s*(?:#.*)?$") {
    Add-ValidationError "Platform CI workflow must pin actions/checkout to a full commit SHA."
}
if ($workflow -notmatch "(?ms)^permissions:\s*\r?\n\s+contents:\s*read\s*$") {
    Add-ValidationError "Platform CI workflow must use explicit read-only repository permissions."
}
if ($workflow -notmatch "(?m)^\s*persist-credentials:\s*false\s*$") {
    Add-ValidationError "Platform CI workflow must not persist checkout credentials."
}
if ($workflow -notmatch "(?m)^\s*runs-on:\s*ubuntu-24\.04\s*$") {
    Add-ValidationError "Platform CI workflow runner must match the verified toolchain record."
}

if ($validationErrors.Count -gt 0) {
    foreach ($validationError in $validationErrors) {
        [Console]::Error.WriteLine($validationError)
    }
    exit 1
}

Write-Host "Phase 0 validation passed."
Write-Host "PowerShell version: $($PSVersionTable.PSVersion)"
Write-Host "JSON files parsed: $($jsonFiles.Count)"
Write-Host "Markdown files and local links checked: $($markdownFiles.Count)"
Write-Host "ADR structure checked: $($adrFiles.Count)"
Write-Host "Contract names, statuses, JSON Schemas, event names, and examples checked."
Write-Host "Platform CI permissions and immutable action pins checked."
