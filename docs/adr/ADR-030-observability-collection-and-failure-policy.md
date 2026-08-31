# ADR-030: Platform observability collection and failure policy

- Status: Accepted
- Date: 2026-08-31
- Owners: platform engineering
- Supersedes: none
- Superseded by: none

## Context

The services expose health endpoints and a minimal `/metrics` response, but
those responses are inconsistent and do not provide HTTP latency/error
signals. Structured JSON logging and request/correlation headers exist only in
the reference service. There is no platform collector, trace backend, log
backend, dashboard, alert rule, or telemetry failure policy.

`docs/architecture/observability.md` already requires OpenTelemetry,
Prometheus, Grafana, Loki, and Tempo. This ADR selects a bounded implementation
topology while retaining the existing principle that application delivery is
not a production deployment.

## Decision

Create `libs/platform-observability` as a technical library with no domain
models. Every API imports it to provide bounded request/correlation context,
JSON stdout logs, low-cardinality Prometheus HTTP metrics, and optional OTLP
trace/log export. Metrics use route templates rather than raw URLs and never
include customer, order, payment, event, message, exception, or provider
values as labels.

The selected collection topology is:

```text
API /metrics ----------------------------> Prometheus
API JSON stdout --------------------------> container logs
API OTLP traces + logs -> OTel Collector -> Tempo + Loki
Grafana -------------------------------> Prometheus + Loki + Tempo
```

The local topology is an explicit Docker Compose `observability` profile. It
is a development and CI proof harness only: all ports bind to `127.0.0.1`, no
provider credential is used, and no target Kubernetes environment is created.
Application Helm charts continue to deploy only application resources. A
future target environment may install its own collector/backends and point the
documented runtime variables at it.

The application exporter is optional and fail-open. A collector/backend outage
must not fail a request, Kafka record, or Celery task; JSON stdout remains
available and the collector exposes its own health and metrics. The collector
uses a memory limiter and batch processor. Local development samples all
traces; production sampling, storage class, retention, access control,
Alertmanager routing, and backend high availability require a target
environment ADR before deployment.

Use only stable OpenTelemetry core packages. The official Python FastAPI,
HTTPX, SQLAlchemy, Kafka, and Celery instrumentation packages are prereleases
at the selected API/SDK release and are therefore rejected by repository
policy. Instrumentation is manual and limited to stable APIs. The upstream
Python logging signal is still marked developmental despite the selected stable
core package version; OTLP log export is therefore an optional bounded wrapper
around canonical JSON stdout, rather than a required delivery dependency.

## Consequences

### Positive

- Every API uses one response-safe request/correlation convention and exports
  the same HTTP request/count/latency/error metric names.
- Metrics, logs, and traces have one local collection path and Grafana
  datasource configuration is versioned with the repository.
- The implementation avoids unreviewed auto-instrumentation monkey patching
  and retains service ownership boundaries.

### Negative and risks

- Telemetry consumes CPU, memory, network bandwidth, and storage; the local
  profile is deliberately not an HA or capacity proof.
- OpenTelemetry logging can export records asynchronously. It augments rather
  than replaces JSON stdout, so a backend outage can create bounded exporter
  drops without silently hiding operational logs.
- A trace can begin at an HTTP boundary today, but durable outbox records do
  not yet persist W3C parent context. Their canonical correlation/causation and
  trace identifiers remain diagnostic context; a future event-envelope change
  must use compatible span links or an additive header persistence design.

## Alternatives considered

- Use the official automatic instrumentation packages: rejected because the
  currently available package line is prerelease.
- Send applications directly to Grafana backends: rejected because a Collector
  centralizes batching, retries, filtering, and backend-specific routing.
- Put observability backends inside the application Helm release: rejected
  because retention, access, scaling, and lifecycle differ from application
  workloads and no target Kubernetes environment has been selected.
- Label metrics by request ID, raw path, event ID, or exception message:
  rejected because these are high-cardinality and can expose sensitive data.

## Compatibility and migration

No API, event schema, database schema, business ownership, or workload
contract changes. `/metrics` remains public inside the platform network but
now returns the Prometheus content type and standard metric families instead
of a service-specific synthetic availability gauge. Prometheus own `up` metric
continues to represent scrape availability.

Exporter activation is configuration-only through
`PLATFORM_OBSERVABILITY_ENABLED` and `PLATFORM_OTLP_GRPC_ENDPOINT`. The default
is disabled, preserving current local and Kubernetes behavior when no
collector exists. Roll back by disabling that variable or by returning to a
compatible application image; no database rollback exists or is needed.

## Validation

- Unit tests verify response headers and that raw path parameters do not become
  metric labels.
- API tests verify `/metrics` serves Prometheus output and Chat retains its
  domain-specific counters.
- Compose profile validation checks Collector, Prometheus, Loki, Tempo, and
  Grafana configuration syntax.
- The `scripts/observability_smoke.ps1` runtime harness starts from a healthy
  profile, emits a request, and verifies collection through Prometheus and
  Tempo/Loki query APIs without claiming a production deployment.
- Alert rules contain owner, severity, and a local runbook URL. Their numeric
  thresholds are provisional until target-environment baselines exist.

## Related material

- [Observability architecture](../architecture/observability.md)
- [Phase 11 plan](../development/phase-11-plan.md)
- [Observability runbook](../runbooks/observability.md)
- [Dependency policy](../development/dependency-policy.md)
