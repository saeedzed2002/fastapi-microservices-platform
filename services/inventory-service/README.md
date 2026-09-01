# Inventory Service

Inventory owns durable stock quantities, reservations, and the immutable
movement ledger for each SKU. The management API is restricted to `admin`.

Every adjustment and Saga reservation locks the stock row before changing it.
PostgreSQL constraints prevent negative stock or a reserved quantity above
on-hand stock. `order.created.v1` creates a reservation and emits either
`inventory.reserved.v1` or `inventory.reservation_failed.v1`; `payment.failed.v1`
releases a live reservation exactly once. `payment.succeeded.v1` commits the
reservation and decreases `on_hand`. `payment.refunded.v1` returns committed
stock only for the compatible confirmed-but-undelivered refund path. A
delivered-order return is different: `order.return_received.v1` restores its
immutable SKU/quantity snapshot once per return identifier, while a correlated
refund outcome with `return_request_id` is financial-only and must never create
a second stock movement. The Inbox, reservation effect, ledger entry, and
Outbox fact commit together.

## API

- POST /api/v1/inventory/stock-items
- GET /api/v1/inventory/stock-items/{sku}
- POST /api/v1/inventory/stock-items/{sku}/adjustments
- GET /api/v1/inventory/stock-items/{sku}/movements
- POST /api/v1/inventory/admin/reconcile-confirmed-reservations

The reconciliation endpoint is restricted to `admin` and consults Order only
through its authenticated REST recovery contract. It never reads Order's
database.

## Operations and verification

`GET /health/live`, `GET /health/ready`, and `GET /metrics` provide process,
database, and Prometheus observability. Apply the schema with
`pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-inventory`; run
focused checks with
`uv run --package inventory-service pytest services/inventory-service/tests -q`.
