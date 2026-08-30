# ADR-026: Media upload lifecycle cleanup and Catalog attachment validation

- Status: Accepted
- Date: 2026-08-30
- Owners: platform engineering
- Supersedes: none
- Superseded by: none

## Context

The direct-to-object-storage upload flow creates a Media metadata record before
the client receives a presigned `PUT` URL. A client may abandon the flow before
uploading bytes, or upload bytes and fail before calling completion. Without a
bounded cleanup lifecycle, those `pending` records and potentially unreferenced
objects accumulate indefinitely.

Catalog stores opaque Media asset identifiers rather than querying Media's
database. Before this decision, Catalog did not verify an asset's readiness,
purpose, or owner before creating a product-media association. A cleanup worker
therefore could not safely assume every pending asset is unattached.

## Decision

Media owns abandoned-upload cleanup. A Celery Beat scheduler periodically asks
Media to select `pending` assets older than the configured retention period.
The selection locks each Media row with `SKIP LOCKED`, changes it to
`deletion_pending`, and writes a `media.delete_asset.v1` task intent in the
same Media transaction. The existing Media task dispatcher delivers that
intent to the Media worker.

The worker loads a `deletion_pending` asset and its derivative object keys,
releases the database session, deletes the original and derivative objects from
object storage idempotently, then opens a new transaction to delete derivative
metadata and mark the asset `deleted`. No database transaction is held across
object-storage I/O. A failed object-storage deletion leaves the asset in
`deletion_pending`, so a Celery retry can safely resume it. The next scheduled
reaper run re-enqueues an old `deletion_pending` asset after the retry interval
if a worker exhausted retries or was unavailable.

The initial cleanup policy applies only to `pending` uploads. Failed or
`uploaded` assets need an operator-reviewed retention policy and are not
silently removed by this job.

Before Catalog writes a product-media association, it makes a synchronous call
to Media's internal versioned endpoint. Catalog signs a proof over owner,
asset, and expiry with a shared secret. Media verifies that proof and accepts
only a non-deleted `ready` asset with `purpose=product_image` and the same
owner. Catalog performs this network call before its database access, so a
Catalog transaction is never held across the service call. After deployment,
pending assets are unreferenced by construction and can be reaped without
Media reading Catalog's database.

## Consequences

### Positive

- Abandoned presigned uploads no longer grow Media metadata and object storage
  without a bounded reclamation path.
- Cleanup delivery is durable and retry-safe rather than depending on a direct
  scheduler-to-worker publish.
- Catalog retains an opaque Media reference and does not cross the database
  boundary.
- Product media cannot point to another user's asset, a non-product image, or
  an unprocessed upload.

### Negative and risks

- Catalog product-image attachment now depends synchronously on Media. Media
  unavailability returns `503` and correctly prevents a weak association.
- Cleanup needs exactly one Beat scheduler per deployment. Multiple schedulers
  can enqueue redundant periodic checks, although row locks prevent a single
  pending asset from producing duplicate cleanup intents.
- Existing historical associations created before this validation must be
  audited before enabling cleanup. The local audit found no stale pending asset
  referenced by Catalog.
- The `uploaded` state can still become stuck when processing delivery fails;
  it is intentionally not conflated with abandoned upload authorization.

## Alternatives considered

- Delete all objects under the `uploads/` prefix with an object-store lifecycle
  rule: rejected because ready originals share that prefix and would be deleted.
- Have Media query Catalog's database before cleanup: rejected because it
  violates database ownership and creates a fragile cross-service dependency.
- Delete the Media row before object storage: rejected because an object-store
  failure would orphan bytes without durable retry state.
- Trust client-provided asset IDs in Catalog: rejected because it permits
  owner, purpose, readiness, and cleanup races.
- Add a Kafka Media projection in Catalog: rejected for the initial release;
  the attachment command needs immediate ownership/readiness validation, while
  the endpoint is small, bounded, and protected with a short-lived proof.

## Compatibility and migration

Media migration `0003_media_cleanup_index` adds the `(status, created_at)`
index used by bounded cleanup scans. It does not alter existing records.

The new internal endpoint is versioned under `/api/internal/v1` and described
by `contracts/openapi/media-catalog-attachment.v1.openapi.json`. It does not
change an existing customer-facing API. Catalog's existing product-media
command gains stricter validation: callers must use a ready, owner-scoped
product image.

Deploy Media API, Media worker, and one Media Beat scheduler with the same
cleanup and proof configuration before deploying Catalog. Rotate the Catalog-
Media secret with Media's optional previous-secret overlap; Catalog always
signs with the current secret.

## Validation

- Unit tests cover HMAC proof verification, durable cleanup intent creation,
  cleanup finalization, and dispatcher routing for both Media task types.
- Catalog tests cover the Media gateway's successful and unavailable-asset
  paths.
- Compose validation confirms the single `media-beat` scheduler and matching
  local configuration.
- The Media migration is applied from the workspace and the changed API,
  workers, and scheduler are recreated before integration validation.

## Related material

- Contract: `contracts/openapi/media-catalog-attachment.v1.openapi.json`
- Runbook: `../runbooks/media-upload-lifecycle.md`
- Architecture: `../architecture/service-boundaries.md`
- Earlier decision: [ADR-012](ADR-012-phase-3-media-reference-boundary.md)
