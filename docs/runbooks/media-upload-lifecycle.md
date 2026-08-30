# Media upload lifecycle

## Scope

Media owns the metadata and object bytes for direct uploads. The client must
authorize, upload, and complete an asset. A completed image becomes `uploaded`,
is processed asynchronously, then becomes `ready` or `failed`.

`pending` records older than `MEDIA_ABANDONED_UPLOAD_RETENTION_SECONDS` are
abandoned authorizations. The `media-beat` scheduler runs at
`MEDIA_ABANDONED_UPLOAD_REAP_INTERVAL_SECONDS`, creates a durable
`media.delete_asset.v1` task intent for each bounded batch, and the Media
worker removes the original and derivative objects before marking the record
`deleted`.

## Configuration

Keep these values consistent on the Media API, `media-worker`, and
`media-beat`:

```env
MEDIA_ABANDONED_UPLOAD_CLEANUP_ENABLED=true
MEDIA_ABANDONED_UPLOAD_RETENTION_SECONDS=86400
MEDIA_ABANDONED_UPLOAD_REAP_INTERVAL_SECONDS=3600
MEDIA_ABANDONED_UPLOAD_CLEANUP_BATCH_SIZE=100
MEDIA_CATALOG_ACCESS_SECRET=<current-shared-secret>
```

Set `CATALOG_MEDIA_BASE_URL` and `CATALOG_MEDIA_INTERNAL_ACCESS_SECRET` on
Catalog. The two current secrets must match. During a secret rotation, set
`MEDIA_CATALOG_ACCESS_PREVIOUS_SECRET` only for the overlap period, roll out
Catalog with the new current secret, validate attachments, then remove the
previous value.

Run exactly one `media-beat` instance for a deployment. Scale `media-worker`
instances as needed; row locks and asset state make cleanup execution safe
across workers.

## Immediate checks

1. Inspect `media-beat` for scheduled reaper delivery and `media-worker` for
   `media_service.delete_asset` completion or retry.
2. Inspect Media task intents by status. A durable `pending` or `dispatching`
   intent indicates delivery work; `deletion_pending` is retryable and must not
   be manually converted to `deleted`.
3. Confirm object storage connectivity before changing Media metadata. Do not
   remove database rows directly: that would orphan object bytes.
4. If Catalog rejects an image attachment, check that the asset belongs to the
   caller, has `purpose=product_image`, and is `ready`. Check the shared secret
   only after those lifecycle conditions.

## Recovery

1. For a scheduler outage, restore the single scheduler. It is safe for the
   next run to select the remaining old `pending` assets.
2. For an object-storage outage, restore access and let the worker retry.
   Retain `deletion_pending`; it is the durable retry marker, and the next
   reaper interval re-enqueues an old pending deletion if retries were exhausted.
3. For a task-dispatcher outage, restore the Media API dispatcher. Existing
   `media.delete_asset.v1` intents remain pending and will be delivered.
4. Investigate stale `uploaded` or `failed` assets separately. They are not
   abandoned authorization records and must not be purged by the pending-upload
   reaper without a dedicated retention decision.
