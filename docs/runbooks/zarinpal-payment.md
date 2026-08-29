# Zarinpal payment recovery

## Detection

Investigate when Payment returns `502`, `503`, or `409` for a Zarinpal start
or callback, when an order remains `PAYMENT_PENDING` past the configured
window, or when a provider-panel transaction disagrees with the Payment
intent. Correlate only by local `order_id`, Payment intent ID, persisted
authority, or provider reference. Never copy merchant IDs, bearer tokens, raw
provider responses, or customer payment details into tickets or logs.

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
refund and customer support; this repository has no automatic refund workflow.

## Verification

- A normal verified callback returns `payment_status: succeeded`, has a
  provider reference, and produces one published `payment.succeeded.v1`.
- A cancelled or rejected callback leaves the intent retryable while it is not
  expired and produces no terminal payment event.
- An expiry has one `payment.failed.v1` outbox record; Order becomes
  `CANCELLED` and Inventory releases the reservation after normal Kafka
  delivery.
- A repeated successful callback does not create a second outbox success row.

## Escalation and follow-up

Escalate provider discrepancies, unknown `REQUESTING` outcomes, and every
`LATE_SUCCESS` with the local IDs and timestamps only. Do not state that a
bank transfer is settled solely from a redirect or provider request response.
Record the reconciliation decision and consider a dedicated refund workflow if
manual cases recur.
