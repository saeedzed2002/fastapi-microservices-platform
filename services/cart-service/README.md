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

`POST /api/v1/carts/me/consume` is used after Payment has returned a
provider redirect. It removes only the checked-out quantities and requires the
cart version returned by the earlier read, so a concurrent cart edit is never
silently deleted.
