# ADR-008 — Use an S3-compatible object-storage abstraction

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

Avatars, product images, Chat attachments, generated invoices, and temporary uploads are large binary objects. Storing them in PostgreSQL would bloat tables, WAL, replication, and backups and would force API services to proxy large transfers.

## Decision

Store binary objects in S3-compatible storage. Application code depends on an `ObjectStorage` port; infrastructure provides an `S3ObjectStorage` adapter. Use MinIO initially for local/self-hosted development without exposing MinIO-specific behavior to business logic.

Use short-lived, narrowly scoped presigned URLs for direct client upload/download where appropriate. PostgreSQL stores ownership, key, size, content type, checksum, lifecycle, and timestamps.

## Consequences

### Positive

- File transfer scales independently from API processes and relational databases.
- AWS S3, Cloudflare R2, Backblaze B2, or another compatible provider can replace MinIO through configuration/adapter validation.
- Storage lifecycle is explicit and observable.

### Negative and risks

- S3-compatible providers differ in signing, checksums, multipart, and lifecycle behavior.
- Orphan objects and metadata require reconciliation.
- Presigned URLs require strict authorization, expiry, key scope, and upload validation.

## Alternatives considered

- PostgreSQL binary columns: rejected for operational and transfer cost.
- Durable container filesystem: rejected because pods are ephemeral.
- MinIO-specific business APIs: rejected because they prevent provider portability.

## Compatibility and migration

Provider changes preserve application-facing `ObjectStorage` semantics and stable metadata. Before cutover, the new adapter must pass the compatibility suite; existing objects are copied and checksum-verified or served through a controlled dual-provider transition without changing domain ownership.

## Validation

- Integration tests cover presigning, direct transfer, metadata verification, provider outage, cleanup, and authorization.
- Object bytes never appear in relational columns or application logs.

## Related material

- [Media and invoice flows](../diagrams/media-and-invoice.md)
- [Service boundaries](../architecture/service-boundaries.md)
- [Security baseline](../architecture/security-baseline.md)
