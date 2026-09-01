# Reference Service

`reference-service` is an executable, non-domain foundation probe. It proves
the shared HTTP runtime before a business capability depends on it: structured
logging, request/correlation propagation, health endpoints, Prometheus metrics,
configuration, a non-root image, and the delivery path.

It owns no business aggregate, database, migration, Kafka event, Celery task,
or cross-service workflow. It must never become a convenience API for domain
logic or a shared persistence boundary.

## API

- `GET /api/v1/reference` returns the service name, version, environment,
  request ID, and correlation ID observed by the HTTP middleware.
- `GET /health/live` reports process liveness.
- `GET /health/ready` reports that this dependency-free probe can serve.
- `GET /metrics` exposes Prometheus metrics through the shared observability
  library.

The reference endpoint is routed through the local edge at
`https://localhost/api/v1/reference`. It is not an authentication or business
API and carries no customer, order, payment, or operational secrets.

## Runtime and operations

Configuration uses the `PLATFORM_` prefix: `PLATFORM_ENVIRONMENT`,
`PLATFORM_LOG_LEVEL`, `PLATFORM_SERVICE_NAME`, and
`PLATFORM_SERVICE_VERSION`. Compose supplies a full platform dependency graph
for topology consistency, but the service's readiness check intentionally does
not query PostgreSQL, Kafka, RabbitMQ, Redis, or object storage.

Run its focused checks with:

```powershell
uv run --package reference-service pytest services/reference-service/tests -q
```

The service has no migration command and no worker process. Its image is built,
scanned, and published with the other independently deployable service images;
the repository CI and the disposable `Kind` health smoke test provide the
delivery evidence.

## Related material

- [Architecture overview](../../docs/architecture/overview.md)
- [Observability model](../../docs/architecture/observability.md)
- [Platform CI](../../.github/workflows/platform-ci.yml)
