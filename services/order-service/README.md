# Order Service

Order owns immutable checkout records, order items, state history, API
idempotency, and Order-owned Outbox and Inbox records. It does not own current
catalog prices, customer profiles, stock, or payments.

`POST /api/v1/orders` first obtains authenticated, authoritative Catalog variant
and Customer address/contact-email snapshots over REST, before opening its local
transaction. A missing contact email rejects checkout rather than creating an
invalid delivery recipient. The transaction persists the order and
`order.created.v1`.

Kafka state transitions are `PENDING` -> `INVENTORY_RESERVED` ->
`PAYMENT_PENDING` -> `CONFIRMED`. Insufficient inventory or a terminal payment
failure ends the order in `CANCELLED`. An Inbox guard and the state machine
prevent duplicate or late facts from repeating effects or resurrecting a
terminal order.

After `CONFIRMED`, the service consumes its own durable confirmation fact with
an independent consumer group. It owns the Invoice metadata, deterministic PDF
object key, task intent, and `invoice.generated.v1` Outbox record. It does not
own email delivery.

## API

- `POST /api/v1/orders` with `Idempotency-Key`
- `GET /api/v1/orders`
- `GET /api/v1/orders/{order_id}`
- `GET /api/v1/orders/admin`
- `GET /api/v1/orders/admin/{order_id}`
- `GET /health/live`
- `GET /health/ready`
