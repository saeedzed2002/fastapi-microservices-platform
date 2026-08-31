# Local observability profile

The `observability` Docker Compose profile is a local collection and diagnosis
tool. It does not represent a production telemetry topology and must not be
exposed on a public network.

Start the platform and the profile with OTLP export enabled from PowerShell:

```powershell
$env:PLATFORM_OBSERVABILITY_ENABLED = "true"
docker compose -f .\infrastructure\compose\docker-compose.yml --profile observability up -d --build
```

The local endpoints are bound only to `127.0.0.1`:

- Grafana: `http://127.0.0.1:3000`
- Prometheus: `http://127.0.0.1:9090`
- Loki: `http://127.0.0.1:3100`
- Tempo: `http://127.0.0.1:3200`
- Collector health: `http://127.0.0.1:13133`

Grafana's local administrator is `admin` and the password is the committed
development-only placeholder `observability-local-only`. Do not reuse it in a
target environment. Application telemetry is disabled by default; set
`PLATFORM_OTLP_GRPC_ENDPOINT` only when the selected Collector endpoint differs
from `otel-collector:4317`.

After the profile and platform report healthy, run the bounded end-to-end proof:

```powershell
pwsh -NoProfile -File .\scripts\observability_smoke.ps1
```

It waits for an initial API response, then creates a request with a unique
correlation ID, verifies the matching Prometheus service metric, and verifies
its returned W3C trace ID in the Tempo trace and Loki JSON log. A failure is
local telemetry evidence only; it does not prove an application outage or a
production-ready deployment.

The profile has bounded local filesystem retention: `15d` in Prometheus and
`7d` in Loki and Tempo. Delete local named volumes only when their diagnostic
data is no longer required.
