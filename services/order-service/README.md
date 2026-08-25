# Order Service

Order owns immutable checkout records, order items, state history, API
idempotency, and Order-owned Outbox and Inbox records. It does not own current
catalog prices, customer profiles, stock, or payments.

`POST /api/v1/orders` first obtains an authenticated, authoritative Catalog
variant snapshot and Customer address snapshot over REST, before opening its
local transaction. The transaction persists the order and `order.created.v1`.

Kafka state transitions are `PENDING` -> `INVENTORY_RESERVED` ->
`PAYMENT_PENDING` -> `CONFIRMED`. Insufficient inventory or a terminal payment
failure ends the order in `CANCELLED`. An Inbox guard and the state machine
prevent duplicate or late facts from repeating effects or resurrecting a
terminal order.

## API

- `POST /api/v1/orders` with `Idempotency-Key`
- `GET /api/v1/orders/{order_id}`
- `GET /health/live`
- `GET /health/ready`
