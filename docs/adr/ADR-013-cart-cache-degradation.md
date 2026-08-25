# ADR-013: Cart cache degradation policy

- Status: Accepted
- Date: 2026-08-25

## Context

Cart reads are likely to be frequent, but a cart is durable customer state and
must remain available when the optional Redis infrastructure is unavailable.
The platform rule permits Redis only for disposable state, so a specific
degradation policy is required before Cart Service uses it.

## Decision

Cart Service stores every cart and item in its own PostgreSQL database. Redis is
an optional cache-aside optimization for authenticated cart reads only.

The cache key is namespaced as cart:v1:{customer_id} and has a short TTL.
After every committed cart write, Cart Service invalidates the cache. A Redis
failure is fail-open: the service logs the cache failure and reads PostgreSQL
directly. A cache miss or loss never creates, deletes, or changes durable cart
data.

## Consequences

### Positive

PostgreSQL remains the sole durable source, and Redis loss cannot destroy or
modify cart contents. Short-lived cached reads reduce repeat database work.

### Negative and risks

Cached responses can be briefly stale during a concurrent write race. Cart
totals and cached item contents are explicitly non-authoritative; Phase 5
checkout will load and revalidate durable cart data and authoritative catalog
and inventory information.

## Alternatives considered

- Redis as the primary cart store was rejected because Redis is ephemeral in
  this architecture and cannot be the source of durable business state.
- A write-through cache was rejected because cache availability must not become
  part of the cart write transaction.
- No cache was viable initially but rejected because the cache-aside boundary is
  small, measurable, and safely degrades to PostgreSQL.

## Compatibility and migration

The cache payload is a versioned cart response and the key is namespaced as
cart:v1:{customer_id}. A cache reset is always safe because records remain in
Cart Service PostgreSQL. Future cache-payload changes must use a new key
namespace or remain backward compatible for the TTL window. No event or
cross-service data migration is introduced.

## Validation

Redis state can be deleted or Redis can be unavailable without loss of cart
records. Unit tests verify cache connection errors fall back to PostgreSQL
reads; local runtime validation deletes only the test cart cache key and proves
that the durable item remains available.

## Related material

- Contracts: none; Cart emits no Phase 4 domain event.
- Diagrams: docs/diagrams/README.md
- Runbooks: docs/runbooks/README.md
- Issues: none
