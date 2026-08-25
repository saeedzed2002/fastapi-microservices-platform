# Inventory Service

Inventory owns durable stock quantities and the immutable movement ledger for
each SKU. The Phase 4 API is restricted to inventory administrators.

Every adjustment uses an idempotency key and locks the stock row before
changing it. PostgreSQL constraints prevent negative stock or a reserved
quantity above on-hand stock. Reservation, release, and Kafka Saga events are
deliberately deferred to Phase 5, when Order Service owns the checkout
workflow contract.

## API

- POST /api/v1/inventory/stock-items
- GET /api/v1/inventory/stock-items/{sku}
- POST /api/v1/inventory/stock-items/{sku}/adjustments
- GET /api/v1/inventory/stock-items/{sku}/movements
