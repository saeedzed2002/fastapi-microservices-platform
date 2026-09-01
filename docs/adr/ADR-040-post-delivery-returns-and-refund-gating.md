# ADR-040: Post-delivery returns and physical-stock refund gating

- Status: Accepted
- Date: 2026-09-01
- Owners: order-service, inventory-service, payment-service, platform architecture
- Supersedes: none
- Superseded by: none

## Context

Phase 18 established Shipping as the owner of delivery truth and kept the
customer-facing delivery projection in Order. The existing administrator refund
workflow is appropriate for a confirmed but undelivered order: Payment emits a
durable reversal fact and Inventory restores stock because the merchandise was
not delivered.

That assumption is unsafe after delivery. A provider reversal must not put an
item back into available stock before staff have physically received it. Nor
may an administrator add stock directly in Inventory and then issue a refund:
that loses the customer request, review decision, receipt audit, and causal
link between the physical and financial outcomes.

## Decision

Order owns one full-order ReturnRequest for a delivered order. A customer may
create the request idempotently with a bounded reason. An administrator makes
the approve/reject decision and, only after receiving every returned line,
records receipt. Partial returns, exchanges, and carrier return logistics are
not in this phase.

Recording receipt locks the Order and ReturnRequest locally, persists the
receipt audit, and writes two Order-owned Outbox facts in the same transaction:

1. `order.return_received.v1` carries the immutable SKU/quantity snapshot,
   return identifier, and opaque receiving-administrator subject to Inventory.
   Inventory records its own Inbox entry and restores on-hand stock exactly
   once for that return identifier.
2. The established `order.refund_requested.v1` carries an additive optional
   `return_request_id`. Payment retains ownership of provider reversal and
   propagates the same optional identifier in its refund outcome facts.

Order stores the pre-refund order status and the optional ReturnRequest link on
the durable refund request. A refund failure therefore restores a delivered
return to its prior customer-visible state instead of incorrectly moving it to
`CONFIRMED`. Payment success marks the order refunded; Order records the
ReturnRequest financial outcome from the correlated fact. Inventory treats a
refund fact with `return_request_id` as financial-only and never performs a
second stock restore.

Existing administrator refunds for confirmed, undelivered orders remain
compatible. They have no ReturnRequest identifier and preserve the established
Inventory refund-restock behavior. Zibal refund support remains out of scope:
Payment's existing durable refund-failed result leaves the received return
visible for manual settlement rather than fabricating a provider success.

## Consequences

### Positive

- Physical receipt, stock restoration, and provider reversal have explicit,
  durable owners and auditable states.
- A duplicate customer request, receipt command, or Kafka delivery cannot
  double-restock inventory or double-request a provider reversal.
- Customer Order history exposes the return state without a synchronous query
  to Inventory, Payment, or Shipping.
- Existing pre-delivery refund semantics remain compatible.

### Negative and risks

- Full-order-only returns deliberately reject common commerce features such as
  partial quantities, exchanges, and replacement shipments.
- A refund can fail after stock has been physically restored. The item remains
  available while the durable return record identifies manual financial
  follow-up; retrying a provider reversal is Payment-owned work.
- The receipt event carries SKU and quantity facts to Inventory. It contains no
  delivery address, free-text return reason, payment credential, or provider
  token.

## Alternatives considered

- Restore stock when Payment emits `payment.refunded.v1`: rejected because a
  delivered item may never be returned even if an operator later reverses the
  charge.
- Let Inventory expose a generic return-restock endpoint for Order to call:
  rejected because it would couple an Order transaction to a network call and
  lacks durable consumer recovery.
- Put returns in Shipping: rejected for this phase because no carrier return
  label, reverse-shipment, or warehouse-receipt capability exists. Shipping
  remains the delivery-truth owner but does not own commercial return review.
- Support partial returns immediately: rejected because it requires immutable
  line-level quantities, partial tax/discount allocation, and provider
  partial-refund rules that have not been approved.

## Compatibility and migration

This is an expand-migrate-contract change. New Order return tables, additive
customer/administrator endpoints, and `order.return_received.v1` are added
without changing established Order or Shipping routes. The existing refund
event schemas gain only optional `return_request_id` fields; old producers and
consumers remain valid. New Inventory Inbox and stock-movement idempotency keys
are scoped by return identifier. Existing refund rows without a return link
fall back to their recorded or historical pre-refund status.

## Validation

- Unit-test customer ownership, idempotency, full-order eligibility, decision
  transitions, receipt idempotency, and rejection of delivery-ineligible
  orders.
- Prove that a return receipt writes the Inventory and Payment handoffs with
  one local Order transaction.
- Prove that duplicate return facts restore stock once, and a correlated
  `payment.refunded.v1` does not restore it again.
- Prove refund failure restores the pre-refund delivered state and leaves a
  visible manual-settlement return outcome.
- Run Compose and disposable-Kind E2E coverage from delivered order through
  receipt, stock restoration, and payment outcome.
- Validate API/event contracts, migration heads, static checks, type checks,
  rendered delivery resources, and image scans in CI.

## Related material

- [Phase 19 plan](../development/phase-19-plan.md)
- [Shipping ownership ADR](ADR-039-shipping-ownership-extraction.md)
- [Order query contract](../../contracts/openapi/order-query.v1.openapi.json)
- [Return API contract](../../contracts/openapi/order-returns.v1.openapi.json)
