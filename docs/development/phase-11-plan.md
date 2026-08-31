# Phase 11 Plan — Complete Observability

## Outcome

Deliver consistent application telemetry and a reproducible local collection
stack. Operators can correlate an API request with JSON logs and traces,
inspect standard HTTP and existing Chat metrics, use provisioned dashboards,
and follow owned alert runbooks.

## Scope

- `libs/platform-observability` for structured JSON logs, bounded context,
  low-cardinality HTTP metrics, and optional OpenTelemetry export;
- application-wide `/metrics` output, preserving Chat realtime counters;
- a local `observability` Compose profile containing Collector, Prometheus,
  Loki, Tempo, Grafana, provisioned dashboards, and alert rules;
- architecture decision, dependency selection evidence, alert ownership, and
  a runbook;
- focused unit tests and a runtime smoke harness.

## Non-goals

- selecting a cloud provider, managed telemetry vendor, target Kubernetes
  topology, public Grafana endpoint, SSO, production credentials, or pager
  integration;
- HPA, production retention capacity, multi-zone backend availability, or
  target-environment SLO enforcement;
- changing API/event contracts, database schemas, service ownership, outbox
  atomicity, or Celery acknowledgement behavior;
- promoting the local Compose profile or disposable CI proof into a production
  deployment.

## Delivery sequence

1. Record `ADR-030` and select only stable, officially verified components.
2. Add the technical library and migrate every API from synthetic metrics and
   reference-service-only logging.
3. Add the opt-in collection profile and declarative Grafana/Prometheus assets.
4. Add dashboards, alert rules, and runbook response paths.
5. Validate the lock, static checks, API tests, Compose configuration, and
   telemetry smoke flow.

## Dependency selection

The following releases were reviewed on 2026-08-31 from their official
projects and registries:

| Component | Selected version | Rationale |
|---|---:|---|
| OpenTelemetry Python API/SDK/OTLP gRPC exporter | 1.44.0 | Latest stable core line, Apache-2.0, Python 3.9+ support; used with Python 3.14. |
| Prometheus Python client | 0.26.0 | Official client, stable release, Python 3.9+ support. |
| OpenTelemetry Collector Contrib | 0.159.0 | Latest released Collector line confirmed before the scheduled 0.160.0 release. |
| Prometheus | 3.14.0 | Latest stable release with current security fixes. |
| Grafana | 13.1.0 | Latest stable release reported by the official project. |
| Loki | 3.7.6 | Latest stable patch release with security fixes. |
| Tempo | 2.9.4 | Latest supported stable patch line; Tempo 3 requires a separately reviewed major migration. |

The `opentelemetry-instrumentation-*` packages are `0.65b0` prereleases. They
are deliberately not selected. `uv.lock` pins the Python graph; infrastructure
uses explicit image tags. Any target environment must additionally pin its
chosen image digests and document access, storage, and lifecycle controls.

Official sources: [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/), [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/), [OpenTelemetry Collector releases](https://github.com/open-telemetry/opentelemetry-collector/releases), [OpenTelemetry Python SDK](https://pypi.org/project/opentelemetry-sdk/), [Prometheus Python client](https://pypi.org/project/prometheus-client/), [Prometheus releases](https://github.com/prometheus/prometheus/releases), [Grafana releases](https://github.com/grafana/grafana/releases), [Loki releases](https://github.com/grafana/loki/releases), and [Tempo releases](https://github.com/grafana/tempo/releases).

Owner: platform engineering. Review before target-environment deployment,
backend major upgrade, or 2026-09-30, whichever occurs first.

## Acceptance evidence

- every API emits `platform_http_requests_total` and
  `platform_http_request_duration_seconds`, and database-owning services emit
  bounded query/pool metrics, with safe labels only;
- JSON logs contain service/version/environment and applicable
  request/correlation/trace identifiers without arbitrary extras;
- the `scripts/observability_smoke.ps1` harness waits for the initial HTTP
  response, verifies the emitted service metric, and verifies one returned
  trace identifier across the JSON log and trace query through the configured
  local backends;
- dashboards and alert rules are provisioned from Git and every alert has an
  owner and runbook;
- exporter failure does not affect application request handling;
- CI validates the exact files and reports evidence boundaries accurately.
