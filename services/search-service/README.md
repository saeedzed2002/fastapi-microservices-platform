# Search Service

Search owns a rebuildable, eventually consistent `PostgreSQL` projection of
Catalog products. It never owns or changes the canonical Catalog product,
variant, media, price, or stock records.

## Public API

- `GET /api/v1/search/products` searches only published products with an
  opaque cursor and optional category, brand, currency, and price filters.

The endpoint is public and protected by a Redis-backed per-source-IP limit.
Redis failure is fail-closed with `503`; search is non-critical and must not
silently lose abuse protection.

## Events and recovery

Search consumes `product.created.v1`, `product.updated.v1`, and
`product.deleted.v1` from `fastapi-platform.catalog.events.v1`. Its Inbox and
product tombstones make replay idempotent and prevent stale updates from
resurrecting deleted products. Catalog's Phase 8 migration writes bootstrap
outbox events for pre-existing products, so a newly deployed Search consumer
builds an initial projection from the same durable path as later changes.

If the projection database is restored or intentionally recreated, reset the
`search-service.catalog` consumer group to the earliest Catalog topic offset
before starting the consumer; see the search runbook. Search never queries the
Catalog database.

## Local migration

```powershell
pwsh -NoProfile -File scripts/platform.ps1 -Task migrate-search
```

The isolated `search_service` database is created by the Compose PostgreSQL
initialization for new local volumes. Existing local volumes need the one-time
database creation command documented in the runbook before running Alembic.

## Operations and verification

`GET /health/live` checks the process. `GET /health/ready` checks both the
local projection database and the Redis rate-limit dependency, because a public
search endpoint without its abuse control must not be declared ready.
`GET /metrics` exposes Prometheus metrics. Run focused checks with
`uv run --package search-service pytest services/search-service/tests -q`.
The API process and Catalog Kafka consumer are separate processes; API
readiness is not evidence that the projection is current.
