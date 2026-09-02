# Phase 3 — Catalog & Media

Phase 3 establishes the Catalog and Media bounded contexts without violating
database ownership or making public product reads depend on object storage.

## Delivered

- `catalog-service` owns product, variant, category, brand, pricing,
  attribute, lifecycle, and opaque product-media association data.
- `media-service` owns upload authorization, object bytes, metadata,
  processing, derivatives, signed downloads, and asset lifecycle.
- Catalog stores only opaque Media asset identifiers. It does not import Media
  domain models, query the Media database, or store file bytes.
- Media persists a completed-processing fact in its transactional outbox and
  publishes the versioned `media.ready.v1` event after the derivative is
  durable.
- Product-image attachment validates the asset through a narrow authenticated
  service contract. Before a product-image asset is deleted, Media verifies
  through Catalog that the asset is not still attached to a product.
- Public product-image delivery is owned by Media. It redirects only a ready,
  non-deleted `product_image` asset to a short-lived object-store URL.
- Each service has its own PostgreSQL schema, migration history, API surface,
  container image, operational endpoints, and tests.

## Boundary and consistency rules

- Catalog product reads expose Media-owned delivery paths; callers must not
  treat opaque asset identifiers as URLs.
- The initial `media.ready.v1` event has no consumer group. Kafka retention
  preserves it for a later approved consumer or read projection.
- Binary uploads go directly to object storage with presigned URLs. PostgreSQL
  stores metadata only.
- Media processing is submitted through a durable task intent and is safe to
  retry. A ready API does not prove that the dispatcher and worker are healthy.
- Public media rendering must remain behind the explicit Media authorization
  and delivery contract; no service may bypass it with direct object-store or
  cross-database access.

## Validation

From the repository root:

    pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-catalog
    pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-media
    uv run --package catalog-service pytest services/catalog-service/tests -q
    uv run --package media-service pytest services/media-service/tests -q

The platform validation also checks the versioned event contract, independent
migration heads, and Compose configuration.

## Related decisions

- [ADR-012](../adr/ADR-012-phase-3-media-reference-boundary.md) defines the
  opaque Media-reference boundary.
- [ADR-026](../adr/ADR-026-media-upload-lifecycle-cleanup.md) defines upload
  lifecycle cleanup.
- [ADR-041](../adr/ADR-041-catalog-management-and-public-product-media.md)
  defines the later Catalog-management and public product-media contract.

## Non-goals

Catalog does not own inventory, reservations, checkout pricing guarantees, or
file bytes. Media does not decide product lifecycle, publish Catalog data, or
authorize a client-issued service proof. Those responsibilities remain in
their owning services and explicit contracts.
