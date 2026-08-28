# OpenAPI Contracts

This directory contains the shared API error envelope and reviewed versioned OpenAPI documents grouped by service. `chat-support.v1.openapi.json` is the canonical contract for Chat's customer-support queue operations. `identity-auth.v1.openapi.json` is the canonical public contract for administrator password and customer OTP authentication; internal service endpoints are excluded.

The generated FastAPI OpenAPI document is not accepted as an unreviewed implementation artifact. Contract changes are reviewed for compatibility and exported schemas are validated in CI.

## Error rules

- `error.code` is stable and machine-readable. Clients do not branch on `message` text.
- `error.message` is safe to display and never exposes stack traces, SQL, table names, secrets, or raw provider errors.
- `error.details` contains safe structured context.
- `error.request_id` matches the response header and structured logs.
- HTTP status remains authoritative and is not duplicated as a conflicting body field.
- Relevant standard headers such as `Retry-After` and `WWW-Authenticate` remain intact.
- A downstream error is translated into the calling service's contract rather than passed through blindly.
