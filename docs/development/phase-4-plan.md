# Phase 4 Plan — Inventory & Cart

## Outcome

Phase 4 introduces two independently deployable bounded contexts:

- Inventory Service owns durable SKU stock, row-locked adjustments, and an
  immutable movement ledger.
- Cart Service owns durable customer carts and their opaque Catalog variant
  selections, with an optional Redis cache-aside read path.

## Explicit boundaries

Inventory does not query Catalog, Cart, or Order databases. A SKU is an
Inventory-owned operational identifier. The initial API is administration-only;
it does not yet reserve stock or publish checkout events.

Cart does not query Catalog or Inventory databases and does not treat a cart
as a price, availability, or checkout guarantee. It stores opaque variant IDs
and quantities. Phase 5 will revalidate the durable cart against Catalog and
Inventory through approved service contracts.

## Durability and failure behavior

PostgreSQL is authoritative for both bounded contexts. Inventory serializes
adjustments with a row lock and a caller idempotency key. Database constraints
protect the stock invariants.

Cart invalidates Redis only after its PostgreSQL transaction commits. A Redis
outage is fail-open: reads bypass the cache, writes remain durable, and the
service logs the cache error. The detailed decision is in
[ADR-013](../adr/ADR-013-cart-cache-degradation.md).

## Deferred to Phase 5

The checkout Saga, inventory reservations/releases, stock-expiry handling,
Kafka order/inventory events, Transactional Outbox records for those events,
and payment interactions are deliberately deferred until the Order and Payment
contracts are implemented together.

## Validation

- unit tests validate API health, SKU normalization, zero-adjustment rejection,
  and disabled-cache behavior;
- migrations create service-owned databases, tables, indexes, and constraints;
- local Compose runs services on ports 8005 and 8006;
- runtime verification exercises stock idempotency, durable cart behavior, and
  Redis cache loss.
