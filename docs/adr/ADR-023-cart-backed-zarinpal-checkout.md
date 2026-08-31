# ADR-023: Cart-backed Zarinpal checkout redirect

- Status: Accepted
- Date: 2026-08-29
- Owners: platform engineering
- Supersedes: none
- Superseded by: ADR-034 for the additive routed online checkout path only

## Context

The prior public flow made a customer create an Order, wait for Inventory and
Payment Saga facts, then manually invoke a second Payment endpoint to obtain a
Zarinpal redirect. That is an operational recovery API, not an acceptable
checkout experience. It also failed to make Cart the normal source of the
customer's selected items.

Removing durable Inventory reservation or allowing Cart to authoritatively set
prices would simplify only the Swagger workflow. It would introduce oversell
and mutable-price failures. Payment must still own provider requests and Order
must still own snapshots and the checkout Saga.

## Decision

Order exposes `POST /api/v1/orders/cart/zarinpal`. A customer sends only a
customer-owned address ID and an `Idempotency-Key`. Before its local Order
transaction, Order reads the customer's durable Cart over authenticated REST,
then obtains the existing Catalog and Customer authoritative snapshots. It
writes the immutable Order and `order.created.v1` Outbox fact exactly as in
ADR-014.

After that transaction commits, the request observes durable Order state for a
bounded, configurable interval. When Payment has consumed the successful
Inventory reservation and the Order reaches `PAYMENT_PENDING`, Order makes an
authenticated REST request to Payment's existing Zarinpal start API. Payment
continues to own provider authority, expiry, retries, and callback verification.
Order returns Payment's `redirect_url` to the caller, which the frontend must
immediately navigate to. No database transaction stays open while waiting for
Kafka or calling Cart, Payment, Catalog, Customer, or Zarinpal.

After Payment has persisted a provider authority, Order attempts an
optimistic Cart cleanup using the Cart version read at checkout. Cart removes
only the exact checked-out quantities when that version still matches; a
concurrent cart edit remains untouched. Cleanup failure never suppresses a
valid provider redirect and is logged for the frontend to refresh the cart.

The existing `POST /api/v1/payments/orders/{order_id}/zarinpal` remains a
low-level idempotent recovery/resume endpoint. The standard customer path is
the Cart-backed Order endpoint.

## Consequences

### Positive

- The frontend has one checkout action and receives a direct provider URL.
- Cart becomes the normal checkout selection source while Catalog and Customer
  remain the authoritative validation sources.
- Inventory reservation, compensation, duplicate safety, and payment callback
  verification are retained behind the customer-facing action.
- A retry after a bounded wait or network loss uses the same key and cannot
  create a second order or a second persisted Zarinpal authority.

### Negative and risks

- The initial checkout request can wait up to the configured bound for Kafka
  delivery. A timeout returns `503`; the frontend must retry with the same
  `Idempotency-Key` rather than creating a new order.
- Cart cleanup is deliberately best-effort after provider authority creation.
  It cannot be part of a distributed transaction with Payment. A changed cart
  is preserved and must be refreshed by the client.
- Direct browser navigation remains a frontend responsibility because this is
  a backend-only repository; an API response cannot move a browser itself.

## Alternatives considered

- Requiring the frontend to call Payment after observing `PAYMENT_PENDING` was
  rejected because it leaks Saga timing into the checkout UI.
- Removing reservations or storing stock directly on Catalog products was
  rejected because it breaks Inventory ownership and safe concurrent stock
  changes.
- Letting Cart call Zarinpal was rejected because Cart does not own orders,
  payment authority, or provider callbacks.

## Compatibility and migration

This adds the `order.checkout.v1` API contract without changing existing
events, tables, or public endpoints. Order receives `ORDER_CART_BASE_URL`,
`ORDER_PAYMENT_BASE_URL`, `ORDER_CHECKOUT_REQUEST_TIMEOUT_SECONDS`,
`ORDER_CHECKOUT_REDIRECT_WAIT_SECONDS`, and
`ORDER_CHECKOUT_REDIRECT_POLL_INTERVAL_SECONDS`; Compose injects service DNS
defaults. No migration is needed.

## Validation

- Gateway parsing tests cover malformed Cart and Payment responses, empty
  carts, retryable Cart-version conflicts, and provider redirect validation.
- Order tests cover the bounded payment-ready state observation and existing
  legal Saga transitions.
- Contract validation covers the new public checkout document.
- Local Compose validation confirms the route reaches Payment and returns a
  sandbox redirect when a configured merchant and stock are available.

## Related material

- Contracts: `contracts/openapi/order-checkout.v1.openapi.json`
- Diagrams: `docs/diagrams/checkout-saga.md`
- Runbooks: `docs/runbooks/zarinpal-payment.md`
- Issues: none
