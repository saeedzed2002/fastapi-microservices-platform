[CmdletBinding()]
param(
    [string]$BaseUrl = "https://localhost",
    [string]$PrometheusUrl = "http://127.0.0.1:9090",
    [string]$LokiUrl = "http://127.0.0.1:3100",
    [string]$TempoUrl = "http://127.0.0.1:3200",
    [ValidateRange(1, 60)]
    [int]$Attempts = 20,
    [ValidateRange(1, 30)]
    [int]$DelaySeconds = 2
)

$ErrorActionPreference = "Stop"

function Wait-ForEvidence {
    param(
        [string]$Label,
        [scriptblock]$Check
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            return & $Check
        }
        catch {
            if ($attempt -eq $Attempts) {
                throw "$Label was not available after $Attempts attempts: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

$correlationId = "observability-smoke-$([guid]::NewGuid().ToString("N"))"
$response = Wait-ForEvidence -Label "Reference Service HTTP response" -Check {
    Invoke-WebRequest -Uri "$BaseUrl/api/v1/reference" -Headers @{
        "X-Correlation-ID" = $correlationId
    } -SkipCertificateCheck
}
$traceparent = [string]($response.Headers["traceparent"] | Select-Object -First 1)
if ($traceparent -notmatch "^00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$") {
    throw "Reference Service did not return a valid W3C traceparent header."
}
$traceId = $Matches[1]

$metricQuery = [uri]::EscapeDataString(
    'sum(platform_http_requests_total{service="reference-service"})'
)
$null = Wait-ForEvidence -Label "Prometheus request metric" -Check {
    $result = Invoke-RestMethod -Uri "$PrometheusUrl/api/v1/query?query=$metricQuery"
    if ($result.status -ne "success" -or $result.data.result.Count -lt 1) {
        throw "reference-service metric has not been scraped"
    }
}

$null = Wait-ForEvidence -Label "Tempo trace" -Check {
    $result = Invoke-RestMethod -Uri "$TempoUrl/api/v2/traces/$traceId"
    if ($null -eq $result) {
        throw "trace query returned no document"
    }
}

$logQuery = [uri]::EscapeDataString(
    "{service_name=`"reference-service`"} |= `"$correlationId`" |= `"$traceId`""
)
$null = Wait-ForEvidence -Label "Loki structured log" -Check {
    $result = Invoke-RestMethod -Uri "$LokiUrl/loki/api/v1/query_range?query=$logQuery&limit=20"
    if ($result.status -ne "success" -or $result.data.result.Count -lt 1) {
        throw "correlated JSON log has not arrived"
    }
}

Write-Output "Observability smoke passed for correlation ID $correlationId and trace ID $traceId."
