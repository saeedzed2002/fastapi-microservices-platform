# Phase 5 Plan — Order & Payment

## Outcome

Phase 5 implements the first choreography-based checkout Saga across Order,
Inventory, and Payment with versioned Kafka facts, transactional Outboxes,
durable Inboxes, idempotency guards, and compensation.

## Scope

- Order accepts idempotent authenticated checkout commands, obtains authoritative
  Catalog and Customer snapshots before its transaction, then stores immutable
  order and item records.
- Inventory adds atomic multi-SKU reservations and release compensation.
- Payment owns fake-provider intents and attempts. Its test method codes model
  success and failure without claiming a production provider integration.
- Kafka facts use order_id as their message key and correlation ID:
  order.created.v1, inventory.reserved.v1,
  inventory.reservation_failed.v1, payment.processing.v1,
  payment.succeeded.v1, and payment.failed.v1.

## Explicit non-goals

Tax, discount, shipping price, a real payment processor, webhooks, refunds,
invoice generation, customer notification, and scheduled deadline processing
are not implemented in this phase. Pending-workflow expiry and reconciliation
require a later bounded-context worker decision.

## Critical rules

- No cross-service database query or shared domain model.
- No network call while a service transaction is open.
- Each event consumer records Inbox, business effect, and resulting Outbox
  state in one local transaction before committing the Kafka offset.
- A payment failure releases an Inventory reservation exactly once.
- A late or duplicate terminal payment fact never changes a terminal Order.

## Dependency selection

The existing aiokafka constraint is retained at >=0.14,<0.15; 0.14.0 was
rechecked from the official PyPI release on 2026-08-25. It supports Python 3.10
and newer, has CPython 3.12 wheels, and is compatible with the repository
Python baseline and local Apache Kafka 4.2.0 for the producer/consumer API used
here. Its Apache-2.0 license and upstream documentation were reviewed. The
exact version is resolved by uv.lock and pinned in service images.
