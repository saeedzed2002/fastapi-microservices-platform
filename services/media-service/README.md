# Media Service

Media owns object bytes, upload processing, asset lifecycle, and signed download
URLs. A ready `chat_attachment` remains Media-owned even when Chat stores a
durable reference. Chat first validates the sender through the ordinary
owner-authorized API. For a recipient read, Chat authorizes conversation
membership and calls `POST /api/internal/v1/media/chat-attachments/{asset_id}/download-url`
with a short-lived HMAC proof. The endpoint verifies the proof, the ready asset,
and its thumbnail derivative before it creates a short-lived URL. It never
queries Chat data or accepts a client-issued proof.

Media owns upload authorization, object metadata, completion verification, image-processing lifecycle, derivatives, and storage cleanup orchestration. Binary bytes are stored in S3-compatible object storage, not PostgreSQL.

## Upload lifecycle

1. An authenticated user requests an upload authorization.
2. The service persists a pending metadata record and returns a presigned PUT URL.
3. The client uploads directly to the object store.
4. The client calls complete; Media verifies object size and content type.
5. In one database transaction Media marks the asset uploaded and records a durable MediaTaskIntent.
6. The dispatcher submits idempotent processing work to the Media Celery queue.
7. A publish attempt is bounded to 10 seconds; a timeout returns the durable intent to pending. A later retry may deliver a duplicate task, which the worker accepts idempotently.
8. The worker creates a thumbnail, marks the asset ready, and writes media.ready.v1 to the transactional outbox.

The Phase 3 active event has no consumer yet. It is intentionally durable and replayable for the later Chat and edge/read-projection integrations. Catalog stores opaque asset identifiers and never consumes a Media database.

## API

- POST /api/v1/media/uploads
- POST /api/v1/media/assets/{asset_id}/complete
- GET /api/v1/media/assets/{asset_id}

Only the owner identified by the access token can complete or inspect an asset.

The two `/api/internal/v1/media/...` endpoints are not browser APIs. Chat uses
the chat-attachment download endpoint with a short-lived `X-Chat-Access-Proof`;
Catalog uses the catalog-asset availability endpoint with its corresponding
short-lived proof. Those proofs authorize a narrow operation and never replace
the caller's ownership or membership checks.

## Operations and verification

`GET /health/live`, `GET /health/ready`, and `GET /metrics` are available for
operations. Apply the Media schema with
`pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-media` and run
focused checks with
`uv run --package media-service pytest services/media-service/tests -q`.
The API process, task dispatcher, and Celery worker are separate Compose
processes; a ready API alone is not evidence that pending media work is being
processed.
