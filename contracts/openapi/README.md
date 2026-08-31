# OpenAPI Contracts

This directory contains the shared API error envelope and reviewed versioned OpenAPI documents grouped by service. `chat-support.v1.openapi.json` is the canonical contract for Chat's customer-support queue operations. `identity-auth.v1.openapi.json` is the canonical public contract for staff password and customer OTP authentication; `identity-admin.v1.openapi.json`, `customer-profile.v1.openapi.json`, and `order-query.v1.openapi.json` define staff lifecycle, customer contact profile, and read-only order queries. `catalog-reviews.v1.openapi.json` defines moderated product reviews and one-level replies; its public representation does not expose author identifiers or moderation state. `order-checkout.v1.openapi.json` defines customer checkout commands, including Cart-backed Zarinpal and provider-routed online redirects. `payment-zarinpal.v1.openapi.json` preserves Payment's explicit Zarinpal start and callback API; `payment-online.v1.openapi.json` defines the additive Payment-owned provider-routing path and verified Zibal browser return. `media-catalog-attachment.v1.openapi.json` is the reviewed internal contract that Catalog uses to verify a ready, owner-scoped product image before persisting an opaque reference. Other internal endpoints are excluded unless they coordinate a durable cross-service ownership boundary.

The generated FastAPI OpenAPI document is not accepted as an unreviewed implementation artifact. Contract changes are reviewed for compatibility and exported schemas are validated in CI.

## Error rules

- `error.code` is stable and machine-readable. Clients do not branch on `message` text.
- `error.message` is safe to display and never exposes stack traces, SQL, table names, secrets, or raw provider errors.
- `error.details` contains safe structured context.
- `error.request_id` matches the response header and structured logs.
- HTTP status remains authoritative and is not duplicated as a conflicting body field.
- Relevant standard headers such as `Retry-After` and `WWW-Authenticate` remain intact.
- A downstream error is translated into the calling service's contract rather than passed through blindly.
