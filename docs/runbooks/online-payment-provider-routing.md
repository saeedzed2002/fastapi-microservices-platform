# Online payment provider routing recovery

## Detection

Use this runbook when the `online` Cart checkout returns `502`, `503`, or
`409`; when an online intent remains `REQUESTING`; or when a provider panel
does not agree with the Payment-owned attempt history. Correlate only by
`order_id`, Payment intent ID, provider name, opaque authority or `trackId`,
and timestamp. Never copy merchant identifiers, bearer tokens, complete
provider payloads, or payment details into logs or tickets.

## Immediate checks

1. Confirm Payment, Order, PostgreSQL, and Kafka outbox health.
2. Confirm both registered public callback routes, not only the local edge
   examples: `/api/v1/payments/zarinpal/callback` and
   `/api/v1/payments/zibal/callback`.
3. Inspect the Payment-owned intent and all attempts by `order_id`; do not
   query the Order database from Payment tooling.
4. Match a provider panel record only to the same provider and persisted
   opaque token. A browser query parameter is never settlement proof.

## Safe recovery

### Definite Zarinpal rejection

Payment records the rejected Zarinpal attempt before it creates a Zibal
attempt. If Zibal returns a redirect, the customer can resume the same
`online` start endpoint and receives that persisted redirect. Do not manually
create another attempt or rerun the Zarinpal request.

### `REQUESTING`

Do not automatically retry or fall back. The provider may have accepted the
request while its response was lost. Reconcile the exact amount and opaque
token in the relevant provider panel. If a transaction exists without a local
token, keep the Order unconfirmed and escalate for manual reconciliation. If
no provider transaction exists, an authorized operator can resolve the local
attempt through the normal expired/cancelled recovery process before allowing
a new customer payment start.

### Browser return and verification

The Zibal callback only locates the local attempt. Payment verifies the saved
`trackId` with Zibal before publishing `payment.succeeded.v1`; never treat a
browser return as payment proof. A verification failure reopens an unexpired
intent without creating a second provider request. A repeated successful
callback must not create a second outbox success row.

### Expiry, late success, and refunds

Expiry marks routed intents terminal and emits `payment.failed.v1`. A late
verified success becomes `LATE_SUCCESS` and must not revive the cancelled
Order. A routed Zarinpal success can use the existing short-window reversal.
For a Zibal success, do not claim a local refund: the current administrator
refund command emits the durable refund-failed outcome and the provider's
settlement workflow requires manual handling until a dedicated refund design
is approved. The same applies after a delivered-order return: receipt and
stock restoration remain auditable, but `REFUND_FAILED` is terminal for the
current API. Do not retry the Order command or modify Order/Payment rows
manually; reconcile through the provider's settlement workflow and record the
customer-support outcome.

## Verification

- The selected provider, redirect, and matching `PENDING_CUSTOMER` attempt
  agree for the same Payment intent.
- A known primary rejection precedes any fallback attempt; an unknown primary
  outcome has no fallback attempt.
- A verified success has one `payment.succeeded.v1` outbox record and normal
  Order/Inventory Saga completion.
- A repeated callback does not duplicate a success fact.
