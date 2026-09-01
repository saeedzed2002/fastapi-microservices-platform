# Post-delivery returns and refund reconciliation

## Scope

Use this runbook for the full-order return workflow after an order is
`DELIVERED`. Order owns the customer request, administrator decision, physical
receipt audit, and customer-visible return projection. Inventory owns the
receipt-gated stock movement. Payment owns the provider reversal and final
financial fact. No operator may query or modify another service's database.

This runbook does not authorize partial returns, exchanges, carrier return
labels, automatic provider retry, generic Inventory adjustments, or direct
Order/Payment database changes.

## Expected workflow

1. The owning customer calls `POST /api/v1/orders/{order_id}/returns` with an
   `Idempotency-Key`. Order accepts one full-order request only for a delivered
   order and records `REQUESTED`.
2. An administrator reviews `GET /api/v1/orders/admin/returns`, then calls the
   decision endpoint with a new idempotency key to set `APPROVED` or
   `REJECTED`.
3. Only for `APPROVED`, an administrator records physical receipt through
   `POST /api/v1/orders/admin/returns/{return_request_id}/receipt` with a new
   idempotency key. Order atomically writes `order.return_received.v1` and
   `order.refund_requested.v1`.
4. Inventory consumes the receipt fact and restores the immutable SKU/quantity
   snapshot once for the return identifier. Payment consumes the refund request
   and emits `payment.refunded.v1` or `payment.refund_failed.v1`.
5. Order records `REFUNDED` or `REFUND_FAILED`. On financial failure, the
   order returns to its recorded pre-refund delivered state; stock remains
   restored because physical receipt already occurred.

The canonical API and event contracts are
[`order-returns.v1.openapi.json`](../../contracts/openapi/order-returns.v1.openapi.json),
[`order.return_received.v1`](../../contracts/events/order.return_received.v1.schema.json),
and the additive refund schemas.

## Immediate checks

1. Read the Order customer or administrator projection and identify the
   `return_request` status, `refund_request_id`, and order status. Do not infer
   financial completion from a successful receipt response.
2. Confirm the physical receipt happened before investigating Payment. A refund
   event never substitutes for receiving merchandise.
3. Inspect the owning service's observability for the correlation ID,
   `return_request_id`, and `refund_request_id`. Do not copy bearer tokens,
   provider payloads, merchant identifiers, or payment credentials into a
   ticket.
4. For a missing asynchronous projection, verify the local Outbox/Inbox health
   and Kafka consumer health for the owning service. Do not republish a new
   event ID or manually insert an Inbox/Outbox row.

## `REFUND_FAILED` handling

`REFUND_FAILED` is a durable terminal result for the current API. It is expected
when a successful online payment was not settled through a reversible Zarinpal
attempt, including Zibal. It is not evidence that the physical return or stock
restoration failed.

Reconcile the persisted provider name, opaque provider authority or track ID,
amount, and timestamp through that provider's settlement process. Record the
customer-support outcome using the approved operational process. Do not retry
the Order receipt/refund command, create a second provider request, or mutate
Order, Payment, or Inventory data manually. A provider-specific retry or refund
API requires a separate approved design with audit and reconciliation rules.

## Verification and evidence boundary

- A receipt replay with the same idempotency key returns the original return;
  a different key conflicts instead of creating another stock movement.
- Inventory shows exactly one receipt-derived movement for the return
  identifier. A correlated `payment.refunded.v1` must not add another movement.
- The Order return is `REFUNDED` only after the correlated Payment fact. A
  failure remains visible as `REFUND_FAILED` while the Order status returns to
  its pre-refund delivered state.

`tests/e2e/test_phase19_returns.py` proves this workflow in the Compose
integration topology. The same portable `returns_workflow.py` runs in the
disposable `Kind` conformance Job after checkout because the Job sets
`E2E_RUN_RETURNS=1`. Neither result proves a real Zarinpal or Zibal merchant
settlement.

## Related material

- [ADR-040](../adr/ADR-040-post-delivery-returns-and-refund-gating.md)
- [Phase 19 plan](../development/phase-19-plan.md)
- [Online payment recovery](online-payment-provider-routing.md)
