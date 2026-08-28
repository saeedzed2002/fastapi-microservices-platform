# ADR-014: Checkout Saga and authoritative snapshots

- Status: Accepted
- Date: 2026-08-25

## Context

Phase 5 introduces the first distributed business workflow. Client and Cart
payloads are not authoritative for price, product availability, or address
data. The checkout choreography must also keep INVENTORY_RESERVED and
PAYMENT_PENDING as independently durable states while tolerating duplicate
and delayed Kafka delivery.

## Decision

Order Service accepts an authenticated checkout command with cart item variant
identifiers, quantities, an address identifier, a payment test-method code, and
an API idempotency key. Before opening its local transaction, Order makes
bounded REST queries to Catalog for active checkout variant snapshots and to
Customer for the caller-owned address snapshot. It rejects missing, inactive,
currency-incompatible, or duplicate variant data. Phase 5 does not implement
discount, tax, shipping, or real provider tokens; the authoritative amount is
the summed Catalog snapshot amount and the immutable Order snapshot records
that limitation.

In one Order transaction the service creates the immutable order, order items,
state history, API idempotency record, and order.created.v1 outbox record.
The order_id is the message key and workflow correlation ID for every Phase 5
event, including Inventory and Payment-produced facts.

Inventory consumes order.created.v1 and atomically writes its Inbox record,
reservation records, stock movements, and exactly one reservation-result
outbox record. On success it emits inventory.reserved.v1; on insufficient
stock it emits inventory.reservation_failed.v1.

Order receiving inventory.reserved.v1 persists only
PENDING to INVENTORY_RESERVED. Payment independently consumes the same
reservation fact, persists a fake-provider payment attempt, and emits
payment.processing.v1 before its terminal result. Order receiving that event
persists INVENTORY_RESERVED to PAYMENT_PENDING. The payment events use the
same Kafka topic and order_id key, so a single Order consumer group observes
them in partition order. payment.succeeded.v1 transitions only
PAYMENT_PENDING to CONFIRMED; payment.failed.v1 transitions only
PAYMENT_PENDING to CANCELLED and Inventory consumes it to release the
reservation.

Each consumer writes a unique Inbox record, guarded business transition, and
any next outbox event in one transaction before committing its Kafka offset.
Duplicate, stale, or terminally inapplicable events are recorded as processed
without repeating the business effect. A terminal late payment success never
resurrects a cancelled order; the fake provider marks it for manual review,
and a real provider integration will require refund policy in a later ADR.

## Consequences

### Positive

- Historical price and delivery-address facts are isolated from later changes.
- Every service retains one local transaction boundary and its own data.
- Payment progression is observable without collapsing two order states.
- The entire workflow is replayable and duplicate-safe through Outbox and
  Inbox records.

### Negative and risks

- Checkout synchronously depends on Catalog and Customer availability before
  acceptance.
- The local fake provider demonstrates idempotency and late-event handling but
  is not a production payment integration.
- Timeout reconciliation is not a distributed transaction and requires a later
  bounded-context worker decision; Phase 5 documents only the safe Outbox and
  consumer recovery path.

## Alternatives considered

- Trusting Cart totals or client-supplied price/address snapshots was rejected
  because mutable client data cannot establish an order's legal history.
- Direct database access to Catalog, Customer, or Cart was rejected because it
  breaks bounded-context ownership.
- A distributed ACID transaction was rejected because it couples independent
  services and cannot cover Kafka or a payment provider.
- Transitioning directly from PENDING to PAYMENT_PENDING was rejected because
  it loses the durable inventory observation.

## Compatibility and migration

The API begins at /api/v1/orders. Every new event has an immutable JSON Schema
payload named with .v1; breaking changes require a new event version. Kafka
topics remain bounded-context topics, while their key is order_id for this
workflow. The fake payment method is a Phase 5-only test contract and must be
replaced by a provider adapter/callback protocol without changing historical
order snapshots. ADR-022 adds the Zarinpal provider path and expiry policy
while preserving those fake methods for deterministic tests.

## Validation

- Unit tests cover legal and illegal state transitions, duplicate API keys,
  duplicate event IDs, and duplicate payment results.
- Integration tests exercise PostgreSQL constraints, Outbox publication, Inbox
  processing, stock reservation contention, and payment compensation.
- End-to-end tests cover success, insufficient stock, payment failure, and
  Kafka replay of each event.
- Operations validation verifies that a late success cannot confirm a cancelled
  order and that Outbox recovery leaves no silently lost business fact.

## Related material

- Contracts: contracts/catalog.json and contracts/events/
- Diagrams: docs/diagrams/checkout-saga.md
- Runbooks: docs/runbooks/README.md and docs/runbooks/zarinpal-payment.md
- Issues: none
