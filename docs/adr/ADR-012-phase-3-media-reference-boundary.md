# ADR-012: Phase 3 media-reference boundary

- Status: Accepted
- Date: 2026-08-25

## Decision

Catalog persists an opaque media asset identifier in its own product_media table. It neither imports Media models nor accesses the Media database. Media publishes media.ready.v1 through its transactional outbox once a derivative is durable.

The event is active in Phase 3 but has no consumer group. Kafka retention and replay preserve it for a later approved consumer such as Chat or a dedicated public-media read projection.

## Consequences

This preserves database ownership and avoids an early synchronous dependency from public Catalog reads to Media. Phase 3 does not expose a public file URL from Catalog; an edge/read projection or service-to-service authorization contract must be approved before public product-media rendering is added.
