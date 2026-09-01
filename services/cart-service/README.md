# Cart Service

Cart owns each customer's durable active cart and its variant selections. It
stores opaque Catalog variant identifiers and quantities only; it does not own
prices, product data, inventory, or checkout validation.

PostgreSQL is the source of truth. Redis is a cache-aside optimization for cart
reads and is deliberately fail-open: loss of Redis bypasses the cache and
continues from PostgreSQL. Cart writes commit before cache invalidation.

## API

- GET /api/v1/carts/me
- POST /api/v1/carts/me/items
- PATCH /api/v1/carts/me/items/{variant_id}
- DELETE /api/v1/carts/me/items/{variant_id}
- DELETE /api/v1/carts/me
- POST /api/v1/carts/me/consume

`POST /api/v1/carts/me/consume` is called by Order after Payment has returned a
provider redirect. It removes only the checked-out quantities and requires the
cart version returned by the earlier read, so a concurrent cart edit is never
silently deleted. All cart endpoints require a `customer` access token.

## Operations and verification

- `GET /health/live` checks process liveness; `GET /health/ready` checks the
  Cart PostgreSQL connection; `GET /metrics` exposes Prometheus metrics.
- Apply the Cart schema with
  `pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-cart`.
- Run focused checks with
  `uv run --package cart-service pytest services/cart-service/tests -q`.

The service has no Kafka consumer or Celery worker in this phase. Redis is not
a source of truth and its outage must not discard a committed Cart change.
