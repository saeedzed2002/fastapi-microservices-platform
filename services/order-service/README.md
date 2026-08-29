# Order Service

Order owns immutable checkout records, order items, state history, API
idempotency, and Order-owned Outbox and Inbox records. It does not own current
catalog prices, customer profiles, stock, or payments.

`POST /api/v1/orders` first obtains authenticated, authoritative Catalog variant
and Customer address/contact-email snapshots over REST, before opening its local
transaction. A missing contact email rejects checkout rather than creating an
invalid delivery recipient. The transaction persists the order and
`order.created.v1`.

`POST /api/v1/orders/cart/zarinpal` is the normal customer payment action. It
reads the authenticated Cart, performs the same authoritative checkout
validation, waits only a bounded interval for the internal reservation Saga,
starts the Payment-owned Zarinpal adapter, and returns `redirect_url`. The
frontend immediately navigates to that URL. A transient `503` must be retried
with the same `Idempotency-Key`, not a new one.

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
- `POST /api/v1/orders/cart/zarinpal` with `Idempotency-Key`
- `GET /api/v1/orders`
- `GET /api/v1/orders/{order_id}`
- `GET /api/v1/orders/admin`
- `GET /api/v1/orders/admin/{order_id}`
- `GET /health/live`
- `GET /health/ready`
