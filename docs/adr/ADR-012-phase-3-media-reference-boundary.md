# ADR-012: Phase 3 media-reference boundary

- Status: Accepted
- Date: 2026-08-25

## Context

Catalog products need to refer to media assets without breaking the service
database-ownership rule. Media processing publishes a durable completion fact,
but Phase 3 intentionally has no approved consumer that can safely expose a
public media URL from Catalog.

## Decision

Catalog persists an opaque media asset identifier in its own product_media table. It neither imports Media models nor accesses the Media database. Media publishes media.ready.v1 through its transactional outbox once a derivative is durable.

The event is active in Phase 3 but has no consumer group. Kafka retention and replay preserve it for a later approved consumer such as Chat or a dedicated public-media read projection.

## Consequences

### Positive

Catalog preserves its database boundary while retaining a stable association
with Media-owned assets.

### Negative and risks

Product reads cannot resolve public media URLs until a separate authorization
and read-model contract is approved. An unconsumed event must be governed by
Kafka retention and monitored once consumers are introduced.
This preserves database ownership and avoids an early synchronous dependency
from public Catalog reads to Media. Phase 3 does not expose a public file URL
from Catalog; an edge/read projection or service-to-service authorization
contract must be approved before public product-media rendering is added.

## Alternatives considered

- Direct Catalog access to the Media database was rejected because it breaks
  bounded-context ownership.
- Storing binary files or public URLs in Catalog was rejected because Media
  owns file lifecycle, authorization, and derivative processing.
- A synchronous Media call on every Catalog read was rejected because it adds
  an early availability dependency to a public read path.

## Compatibility and migration

The product_media relation accepts opaque UUIDs only. The active media.ready.v1
event uses its independent versioned schema and may gain a consumer without a
change to the Catalog API. Any future public-media projection must be deployed
alongside an explicit authorization contract; this decision requires no
cross-database migration.

## Validation

Catalog tests and migrations prove that it stores only the opaque asset ID.
Media's outbox integration test proves that media.ready.v1 is emitted after
durable derivative processing. Contract validation checks the active schema.

## Related material

- Contracts: contracts/events/media.ready.v1.schema.json
- Diagrams: docs/diagrams/README.md
- Runbooks: docs/runbooks/README.md
- Issues: none
