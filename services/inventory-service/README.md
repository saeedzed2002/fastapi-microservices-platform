# Inventory Service

Inventory owns durable stock quantities, reservations, and the immutable
movement ledger for each SKU. The management API is restricted to `admin`.

Every adjustment and Saga reservation locks the stock row before changing it.
PostgreSQL constraints prevent negative stock or a reserved quantity above
on-hand stock. `order.created.v1` creates a reservation and emits either
`inventory.reserved.v1` or `inventory.reservation_failed.v1`; `payment.failed.v1`
releases a live reservation exactly once. `payment.succeeded.v1` commits the
reservation and decreases `on_hand`; `payment.refunded.v1` returns committed
stock. The Inbox, reservation effect, ledger entry, and Outbox fact commit
together.

## API

- POST /api/v1/inventory/stock-items
- GET /api/v1/inventory/stock-items/{sku}
- POST /api/v1/inventory/stock-items/{sku}/adjustments
- GET /api/v1/inventory/stock-items/{sku}/movements
- POST /api/v1/inventory/admin/reconcile-confirmed-reservations
