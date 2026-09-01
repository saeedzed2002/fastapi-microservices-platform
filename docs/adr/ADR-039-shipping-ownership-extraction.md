# ADR-039: Shipping ownership extraction with refund-safe fulfillment fence

- Status: Accepted
- Date: 2026-09-01
- Owners: order-service, shipping-service, platform architecture
- Supersedes: the Order-owned fulfillment portion of ADR-024 after Phase 18 migration completes
- Superseded by: none

## Context

Order currently persists carrier, tracking, and fulfillment status in
`order_fulfillments`. This was appropriate while the application had no
Shipping bounded context, but it conflicts with the stated architecture:
Shipping must own carrier references and fulfillment truth, while Order owns
payment/refund eligibility and customer order history.

A naïve extraction is unsafe. An administrator can currently advance a paid
order while another administrator requests a provider reversal; the existing
Order transaction serializes these paths. Moving shipment state to Shipping
without replacing that fence would permit a refund to start while Shipping is
committing `SHIPPED`, producing a paid/refunded shipment contradiction.

## Decision

Introduce `shipping-service` as the owner of a Shipment aggregate with one
unique `order_id`, carrier, tracking number, fulfillment status, state-change
audit rows, Inbox, and Outbox. Shipping receives the existing
`order.confirmed.v1` fact and creates a `READY` shipment idempotently. It
does not receive a customer delivery address in Kafka and does not integrate a
real carrier in this phase.

Order retains an Order-owned, short-lived fulfillment-transition authorization
record. Before Shipping commits an administrator-requested transition, it
obtains a narrowly scoped authorization from Order. Order locks its local order
row, rejects the request unless the order is still eligible for fulfillment,
and refuses a refund while a valid authorization exists. Shipping commits its
own state and `shipping.status_updated.v1` outbox fact locally; it never holds
an Order transaction across the call.

Order consumes `shipping.status_updated.v1` through its Inbox and updates the
existing `OrderFulfillment` record only as a customer-facing projection. It
also records the corresponding Order transition after validating the event
against the authorization. A delayed or duplicate Shipping fact cannot create
another shipment or bypass refund eligibility.

An authorization whose wall-clock expiry has passed remains `ACTIVE` until
Order obtains a definitive Shipping recovery response for its `command_id`.
Shipping rejects a local commit at or after that expiry. If recovery reports
`NOT_COMMITTED`, Order marks the authorization `RELEASED` and may continue the
refund. If recovery reports the matching committed transition, Order applies
the same Inbox/projection path before rejecting the refund. An unavailable,
malformed, or mismatched recovery response returns a temporary failure and
does not release the financial fence. This avoids the unsafe inference that a
late event means that Shipping never committed.

The existing Order `v1` fulfillment endpoint is a compatibility facade during
the migration. It forwards a caller-authorized, idempotent command to Shipping
and returns a clear unavailable/uncertain result rather than guessing whether
a timeout committed. It is not removed until the facade, projection, and
recovery behavior have Compose and `Kind` evidence.

## Consequences

### Positive

- Carrier/tracking lifecycle has one durable owner without cross-service
  database access.
- Payment reversal keeps a local financial fence and cannot silently race a
  shipment transition.
- Customer Order history remains a local read model and does not synchronously
  depend on Shipping availability.
- Shipment status facts are small and avoid putting delivery-address data on
  Kafka.

### Negative and risks

- A status update is a small distributed workflow with explicit expiry and
  recovery handling, not a one-transaction CRUD endpoint.
- The Order compatibility facade may return a temporary error after an unknown
  network outcome; callers must poll the established Order history endpoint.
- Carrier API integration remains intentionally absent, so administrators enter
  tracking data manually in this increment.

## Alternatives considered

- Keep fulfillment permanently inside Order: rejected because it leaves a
  Shipping bounded context only as an undocumented future claim and prevents
  carrier integration from having a proper owner.
- Let Shipping update status without Order authorization: rejected because a
  refund can race a remote shipment commit.
- Copy Order's delivery-address snapshot into the confirmation event: rejected
  because it expands durable Kafka PII before a carrier integration needs it.
- Have Shipping read the Order database: rejected because it violates the
  service ownership boundary.
- Use a distributed transaction or shared lock: rejected because it couples
  independent services and holds a transaction across network calls.

## Compatibility and migration

This is an expand-migrate-contract change. Existing `order.confirmed.v1` and
`order.fulfillment_updated.v1` remain supported during the transition; their
schemas are not destructively altered. New Shipment tables, Order authorization
records, a new Shipping status fact, and an additive Shipping API are
introduced first. Order keeps its fulfillment table as a projection until
backfill, facade, consumer, and recovery evidence are complete. Only a later
approved contract phase may deprecate the old Order mutation endpoint.

## Validation

- Unit-test Shipment transitions, duplicate confirmation facts, and duplicate
  status facts.
- Prove that concurrent refund and Shipping transitions serialize through the
  Order authorization record.
- Prove expired authorizations neither permit a late transition nor block a
  later refund indefinitely.
- Run Compose E2E for confirmation, shipping, customer projection, and refund
  conflict behavior; repeat the critical workflow in disposable `Kind`.
- Validate all new API and event schemas, migration heads, rendered manifests,
  and image scans in CI.

## Related material

- [Phase 18 plan](../development/phase-18-plan.md)
- [Service boundaries](../architecture/service-boundaries.md)
- [Checkout Saga](../diagrams/checkout-saga.md)
- [ADR-024](ADR-024-two-role-order-administration.md)
- [Order query contract](../../contracts/openapi/order-query.v1.openapi.json)
