# ADR-041: Catalog management and public product media

- Status: Accepted
- Date: 2026-09-02
- Owners: catalog-service, media-service, platform architecture
- Supersedes: none
- Superseded by: none

## Context

Catalog already owned product, category, brand, variant, and product-media
data, but its management surface was incomplete. Brands had no API; product
media could only be attached; variants could not be updated or retired; and
deleting a product physically removed variants, reviews, and media relations.
The public product response exposed opaque Media identifiers, but no public
route could resolve a ready product image. A customer token could also request
a `product_image` upload authorization, despite product media being an
administrator-owned concern.

The platform must keep Catalog as the owner of product relationships and Media
as the owner of asset lifecycle and bytes. Neither service may query the other
service's database or keep a transaction open during a service call.

## Decision

All Catalog management commands for products, categories, brands, product
media, and variants require an Identity-issued access token carrying the
`admin` role. Customers can read only published products, active variants of a
published product, public categories and brands, and approved reviews.

Catalog exposes complete management operations for brands, administrator
product listing and reads, product archive/restore, mutable product-media sort
order and detachment, and mutable/retirable variants. A product deletion is an
archive transition, not a physical delete: it sets `status=archived`, records
`archived_at`, and emits the existing `product.deleted.v1` fact. Restore moves
the product to `draft`; publication remains an explicit command. Categories and
brands are physically deletable only when no child or product reference would
be broken. Variant deletion means `is_active=false`, preserving checkout
history and SKU identity.

Media accepts `purpose=product_image` upload authorization only from an
administrator. Catalog returns a relative `media_urls` entry for every attached
asset. Media's public product-image route resolves only a non-deleted `ready`
product-image thumbnail and redirects to a short-lived object-storage URL; no
object key is exposed by Catalog.

Before deleting a `product_image` asset, Media makes a narrow, signed,
versioned REST query to Catalog. Catalog alone reads its `product_media`
relationship and returns whether that asset is referenced. Media refuses a
referenced asset with `409`; the administrator must detach it from every
product first. The caller owns the asset, and product-image deletion also
requires `admin`. This keeps relationship ownership in Catalog and byte
ownership in Media.

## Consequences

### Positive

- A normal authenticated customer cannot create, change, archive, restore, or
  publish store data, nor authorize or delete product images.
- Storefront clients receive an API URL that resolves product images without
  needing Media ownership credentials.
- Archive/restore and variant retirement retain information needed by order,
  review, and search history.
- Product media has deterministic ordering and an explicit detach operation.
- A ready product image cannot normally be deleted while Catalog still serves
  it.

### Negative and risks

- Product-image deletion now has a bounded Media-to-Catalog dependency. A
  Catalog timeout returns `503`; Media fails closed rather than risking a
  broken storefront image.
- The reference check is a precondition, not a distributed transaction. An
  attachment and deletion racing across services are protected by normal
  command ordering but are not globally serializable. If this operation needs
  stronger concurrency guarantees, introduce a durable attachment lease/event
  protocol rather than holding either database transaction across the network.
- Detached ready assets remain available to their owner until explicitly
  deleted. Automatic cleanup still applies only to abandoned `pending` uploads.

## Alternatives considered

- Leave raw Media deletion unrestricted: rejected because it can leave a
  Catalog product with a dead image URL.
- Make Media query Catalog's database: rejected because it violates database
  ownership.
- Hard-delete products and variants: rejected because it destroys operational
  history and makes restore impossible.
- Give every authenticated customer product-image upload capability: rejected
  because it lets customers create public-store media outside Catalog's
  administration boundary.

## Compatibility and migration

Catalog migration `0006_catalog_management` adds nullable `products.archived_at`,
an administrator-listing index, and uniqueness for a product/media pair. It
does not change existing public product identifiers or event schemas.

Public product responses add `media_urls` and `archived_at`; this is additive.
Consumers must use `media_urls` for browser rendering and continue treating
`media_asset_ids` as opaque identifiers. The public variants endpoint now
returns `404` for draft and archived products and omits retired variants.

Deploy Catalog before enabling Media asset deletion against it. Configure
`MEDIA_CATALOG_BASE_URL` alongside the existing shared
`MEDIA_CATALOG_ACCESS_SECRET`; it must target Catalog's internal service URL.
The public object-storage endpoint used for presigned URLs must be reachable by
the browser, not merely by the Media pod.

## Validation

- Catalog endpoint tests send a real signed customer token to every management
  mutation and expect `403`.
- Media tests reject a customer product-image upload, validate ready-thumbnail
  public delivery, and verify durable deletion intent creation.
- Gateway tests cover signed Catalog-to-Media attachment validation and the
  signed Media-to-Catalog reference-status query.
- Lint, focused Catalog and Media suites, migration upgrade, contract JSON
  validation, and Helm rendering are required before release.

## Related material

- Contracts: `../../contracts/openapi/catalog-products.v1.openapi.json`,
  `../../contracts/openapi/catalog-management.v1.openapi.json`,
  `../../contracts/openapi/media-assets.v1.openapi.json`, and
  `../../contracts/openapi/catalog-media-reference.v1.openapi.json`
- Architecture: `../architecture/service-boundaries.md`
- Runbook: `../runbooks/media-upload-lifecycle.md`
- Earlier decisions: [ADR-012](ADR-012-phase-3-media-reference-boundary.md)
  and [ADR-026](ADR-026-media-upload-lifecycle-cleanup.md)
