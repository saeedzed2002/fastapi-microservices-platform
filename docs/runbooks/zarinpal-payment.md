# Zarinpal payment recovery

## Detection

Investigate when Payment returns `502`, `503`, or `409` for a Zarinpal start
or callback, when an order remains `PAYMENT_PENDING` past the configured
window, or when a provider-panel transaction disagrees with the Payment
intent. Correlate only by local `order_id`, Payment intent ID, persisted
authority, or provider reference. Never copy merchant IDs, bearer tokens, raw
provider responses, or customer payment details into tickets or logs.

The normal frontend command is `POST /api/v1/orders/cart/zarinpal`, not the
low-level Payment start endpoint. It returns a ready provider redirect or a
bounded `503`; retry that `503` with the same `Idempotency-Key`.

## Immediate checks

1. Confirm the Payment service, its PostgreSQL connection, Kafka outbox worker,
   and Order service are ready.
2. Confirm the configured callback is the edge route
   `https://localhost/api/v1/payments/zarinpal/callback` for same-machine local
   testing, or the registered public `HTTPS` URL in a deployed environment.
3. Inspect the Payment intent, its attempts, and unpublished outbox records by
   `order_id`. Check the authoritative Order state through the Order API; do
   not query the Order database from Payment tooling.
4. Compare a provider-panel transaction only with the persisted authority and
   amount. A browser `Status` parameter is not proof of payment.

## Safe recovery

### `REQUESTING`

The provider request may have reached Zarinpal even if Payment did not receive
a response. Do not retry the customer start endpoint automatically and do not
manufacture an authority. Reconcile the amount and order in the provider panel.
If no provider transaction exists, an authorized operator may close the local
attempt according to the normal expired/cancelled recovery policy before a new
customer start. If a charge exists without a persisted authority, keep the
order unconfirmed and escalate for manual refund/reconciliation.

### `PENDING_CUSTOMER` or `VERIFYING`

For `PENDING_CUSTOMER`, the customer may reuse the existing start endpoint; it
returns the same redirect instead of charging again. For `VERIFYING`, do not
send another charge request. Restore provider connectivity and repeat only the
callback verification for the persisted authority. Provider verification is
idempotent; a successful local result emits at most one payment-success fact.
A browser return with a non-`OK` status cannot cancel an attempt already in
`VERIFYING`; Payment returns `409` and leaves verification ownership with the
in-flight callback. This prevents an interleaved browser request from losing a
verified provider charge.

### `EXPIRED` or `LATE_SUCCESS`

Expiry emits `payment.failed.v1`, so Order cancellation and Inventory release
are asynchronous. Wait for the Payment outbox and downstream consumer state
before taking manual action. A later verified provider success is recorded as
`LATE_SUCCESS` and must not confirm the cancelled order. Escalate it for manual
reconciliation and customer support; a normal reversal is only available for a
confirmed order inside the provider's short reversal window.

### `REFUND_PENDING`

An administrator starts the reversal through
`POST /api/v1/orders/admin/{order_id}/refund` using one fresh `Idempotency-Key`.
Order writes `order.refund_requested.v1` and changes to `REFUND_PENDING`; do
not send a fulfillment update while it is in that state. Payment persists the
reversal before calling Zarinpal. A provider success emits
`payment.refunded.v1` and Order becomes `REFUNDED`; a provider rejection emits
`payment.refund_failed.v1` and Order returns to `CONFIRMED`.

If the Payment reversal remains `REQUESTING` after a provider timeout, do not
retry it automatically or fabricate a successful result. Reconcile the local
authority against the provider before a manual recovery decision. This
short-window reversal is not a full or partial refund facility.

## Verification

- A normal verified callback returns `payment_status: succeeded`, has a
  provider reference, and produces one published `payment.succeeded.v1`.
- A cancelled or rejected callback leaves the intent retryable while it is not
  expired and produces no terminal payment event.
- An expiry has one `payment.failed.v1` outbox record; Order becomes
  `CANCELLED` and Inventory releases the reservation after normal Kafka
  delivery.
- A repeated successful callback does not create a second outbox success row.
- A completed reversal has one `payment.refunded.v1` and Inventory has exactly
  one `refund_return` movement for every committed SKU quantity.

## Escalation and follow-up

Escalate provider discrepancies, unknown `REQUESTING` outcomes, and every
`LATE_SUCCESS` with the local IDs and timestamps only. Do not state that a
bank transfer is settled solely from a redirect or provider request response.
Record the reconciliation decision and consider a dedicated refund workflow if
manual cases recur.
