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

`POST /api/v1/orders/cart/online` follows the same Cart and Saga boundary but
asks Payment to choose a provider. Payment prefers Zarinpal and may use Zibal
only after a definitive rejection; Order never selects a provider or stores a
provider token. The same idempotency key must never be reused across the
explicit `zarinpal` and routed `online` methods.

Kafka state transitions are `PENDING` -> `INVENTORY_RESERVED` ->
`PAYMENT_PENDING` -> `CONFIRMED`. Insufficient inventory or a terminal payment
failure ends the order in `CANCELLED`. A Zarinpal refund request transitions
`CONFIRMED` to `REFUND_PENDING`, then to `REFUNDED` or back to `CONFIRMED`.
An Inbox guard and the state machine
prevent duplicate or late facts from repeating effects or resurrecting a
terminal order.

After `CONFIRMED`, the service consumes its own durable confirmation fact with
an independent consumer group. It owns the Invoice metadata, deterministic PDF
object key, task intent, and `invoice.generated.v1` Outbox record. It does not
own email delivery.

Order owns a short-lived fulfillment-transition authorization record. Shipping
obtains that authorization before it commits a local shipment transition. A
still-valid authorization blocks a new refund and the forwarding fulfillment
facade. After expiry, Order obtains the definitive command state from Shipping:
it releases the fence only for `NOT_COMMITTED` and applies the matching
committed fact before rejecting a refund. An unavailable, malformed, or
mismatched recovery response leaves the fence in place and returns a temporary
outcome. Order never exposes its database to Shipping.

## Post-delivery returns

Order owns one full-order `ReturnRequest` for a delivered order. The customer
creates it idempotently; an administrator approves or rejects it, then records
physical receipt only after approval. Receipt writes both
`order.return_received.v1` and `order.refund_requested.v1` with the same local
Order transaction. Inventory independently restores the received SKU snapshot
once, and Payment independently performs the provider-owned reversal.

For a delivered return, a `payment.refund_failed.v1` outcome restores the
customer-visible delivered status and marks the return `REFUND_FAILED`; it must
be reconciled through the provider settlement process, not retried by replaying
an Order command or manually changing Order/Payment rows. A successful outcome
marks the return `REFUNDED`. The existing administrator refund endpoint remains
for the compatible confirmed-but-undelivered path.

## API

- `POST /api/v1/orders` with `Idempotency-Key`
- `POST /api/v1/orders/cart/zarinpal` with `Idempotency-Key`
- `POST /api/v1/orders/cart/online` with `Idempotency-Key`
- `GET /api/v1/orders`
- `GET /api/v1/orders/{order_id}`
- `GET /api/v1/orders/admin`
- `GET /api/v1/orders/admin/{order_id}`
- `PATCH /api/v1/orders/admin/{order_id}/fulfillment`
- `POST /api/v1/orders/admin/{order_id}/refund` with `Idempotency-Key`
- `POST /api/v1/orders/{order_id}/returns` with `Idempotency-Key`
- `GET /api/v1/orders/admin/returns`
- `POST /api/v1/orders/admin/returns/{return_request_id}/decision` with `Idempotency-Key`
- `POST /api/v1/orders/admin/returns/{return_request_id}/receipt` with `Idempotency-Key`
- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`

`POST /api/internal/v1/orders/{order_id}/fulfillment-authorizations` is the
Shipping-only authorization boundary. It is not a browser endpoint and
requires Shipping's short-lived access proof as well as the administrator
bearer token that owns the proposed transition.

## Operations and verification

Apply the Order schema with
`pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-order` and run
focused checks with
`uv run --package order-service pytest services/order-service/tests -q`.
`GET /health/ready` verifies local PostgreSQL; the API process, Kafka
consumer/publisher, invoice dispatcher, and Celery invoice worker are separate
runtime responsibilities. API readiness is not proof that an invoice or an
asynchronous projection has completed.
