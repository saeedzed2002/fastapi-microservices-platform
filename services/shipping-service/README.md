# Shipping Service

Shipping owns shipment state, carrier references, tracking numbers, transition
audit rows, its Inbox and Outbox, and the `shipping.status_updated.v1` fact. It
does not own Order payment/refund state, Inventory stock, customer addresses,
or carrier-provider credentials. Carrier-label purchase, rate shopping,
webhooks, delivery estimates, and reverse logistics remain out of scope.

## Durable workflow

The Kafka worker consumes `order.confirmed.v1` and creates one `READY`
shipment per order. The unique Order reference and Inbox row make duplicate
delivery safe. An administrator can then transition a shipment through
`READY -> PROCESSING -> SHIPPED -> DELIVERED`; `SHIPPED` requires both carrier
and tracking number.

Before committing a transition, Shipping calls the Order-owned authorization
boundary using the administrator's bearer token. It commits the Shipment,
transition audit, and `shipping.status_updated.v1` Outbox row locally only
while that authorization is valid. Order consumes the resulting fact as a
customer-facing projection and retains the financial fence. Shipping never
holds an Order transaction and never reads the Order database.

## APIs

- `PUT /api/v1/shipping/admin/orders/{order_id}/status` requires an `admin`
  bearer token and `Idempotency-Key`. A matching retry returns the original
  committed transition.
- `GET /api/internal/v1/shipping/commands/{command_id}` is an internal Order
  recovery endpoint. It is excluded from OpenAPI and accepts only the
  short-lived `X-Order-Shipping-Proof`; it is not a public client API.
- `GET /health/live`, `GET /health/ready`, and `GET /metrics` provide
  process, PostgreSQL-readiness, and Prometheus observability endpoints.

The public command contract is
[`shipping-commands.v1.openapi.json`](../../contracts/openapi/shipping-commands.v1.openapi.json).
`503` means the Order authorization outcome is unknown: retry only with the
same idempotency key. `409` covers an invalid transition, an expired/denied
authorization, or an idempotency conflict; `422` means a `SHIPPED` command
omitted carrier or tracking data.

## Dependencies and failure behavior

- PostgreSQL stores Shipping-owned business state, Inbox, transition audit, and
  Outbox. Readiness performs a local database query.
- Kafka supplies `order.confirmed.v1` and transports
  `shipping.status_updated.v1`. The dedicated worker enables consumer and
  publisher loops separately.
- Order supplies the short-lived authorization and later reads definitive
  command recovery. An unavailable or invalid authorization is a temporary
  failure; Shipping does not guess whether a remote call committed.

Configuration uses the `SHIPPING_` prefix. The production-relevant values are
`SHIPPING_DATABASE_URL`, `SHIPPING_JWT_SECRET`, `SHIPPING_ORDER_BASE_URL`,
`SHIPPING_ORDER_INTERNAL_ACCESS_SECRET`,
`SHIPPING_ORDER_ACCESS_PROOF_TTL_SECONDS`, and Kafka settings. Known local
credentials are rejected outside `SHIPPING_ENVIRONMENT=local`.

## Local validation

Apply the service-owned migration with:

```powershell
pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-shipping
```

Run focused tests with:

```powershell
uv run --package shipping-service pytest services/shipping-service/tests -q
```

The cross-service transition is exercised by
`tests/e2e/test_phase18_shipping.py` in Compose and by the disposable `Kind`
checkout conformance Job. Those checks prove the asynchronous Order projection;
they do not prove a third-party carrier integration.

## Related material

- [ADR-039](../../docs/adr/ADR-039-shipping-ownership-extraction.md)
- [Shipping command contract](../../contracts/openapi/shipping-commands.v1.openapi.json)
- [Service boundaries](../../docs/architecture/service-boundaries.md)
