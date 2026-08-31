# Security Baseline

Security is enforced at every service boundary and throughout delivery; the edge layer is not the only trust boundary.

## Identity and sessions

- Hash passwords with Argon2id using reviewed, operationally measured parameters.
- Use short-lived signed JWT access tokens with explicit issuer and audience validation.
- Require the issued-at claim, accept no more than two seconds of future issuance for bounded clock skew, and keep expiration validation strict.
- Rotate refresh tokens and detect reuse at the token-family/session level.
- Make logout and revocation semantics explicit, including expiry and Redis-outage behavior.
- Store only hashed refresh-token material where practical.
- Retain only bounded device metadata and an HMAC-protected peer-address digest
  for refresh sessions; never expose or persist a raw address for session UI.
- Rotate signing keys through a documented distribution and overlap process.
- For customer OTP, store the verification hash and abuse controls in Identity
  Redis, retain the raw code only in a separate short-lived Identity delivery
  key, and fail closed when that security state is unavailable. The raw code
  must not enter PostgreSQL, Kafka, RabbitMQ, Celery payloads, logs, or traces.
- Allow password login only for an existing `admin` role.
  Customer registration and sign-in use the phone OTP endpoints.
- Password reset applies only to password-bearing `admin` users, returns a
  non-enumerating response, is Redis cooldown-limited, and stores only a token
  hash durably. The raw reset token follows the same short-lived Identity-only
  delivery pattern as OTP and is consumed on use.

The signing algorithm, JWKS/key-distribution mechanism, claim set, and service-to-service identity model are Phase 2 design decisions.

## Authorization

- Use RBAC for coarse capabilities.
- Enforce resource-level ownership and domain policy inside the owning service.
- Do not trust gateway authorization as sufficient.
- Do not pass broad internal credentials to clients or unrelated services.
- Audit sensitive order, payment, inventory-adjustment, and authentication changes.

## Abuse and request controls

- Configure request, header, and body limits at both edge and service layers.
- Apply Redis-backed rate limits to staff login, OTP, password reset, public search, uploads, and WebSocket connections.
- Document fail-open/fail-closed behavior per limit; authentication abuse controls cannot silently disappear.
- Chat WebSocket connection limits are fail-closed if Redis is unavailable. Chat never accepts bearer tokens in its URL; the first versioned frame authenticates the connection before any Chat operation.
- Use narrow CORS allowlists and explicit credential behavior per environment.
- Apply appropriate security headers and TLS at the edge. Local Nginx accepts only `TLSv1.2` and `TLSv1.3`, forwards a generated request ID and trusted direct-peer address, and applies documented per-instance IP limits. Its password/OTP and WebSocket-upgrade buckets are separate so login abuse on a shared source IP cannot consume a connected customer's Chat-upgrade allowance; these controls do not replace service-owned Redis-backed limits.

## Upload and object security

- Scope presigned URLs to one authorized object and operation with short expiry.
- Validate declared and actual type, magic bytes, size, checksum, dimensions, filename/metadata, and decompression risk.
- Strip EXIF and unnecessary metadata during image processing.
- Keep buckets private and authorize downloads through service policy.
- Define quarantine/malware scanning where asset risk justifies it.
- Reconcile incomplete uploads and orphan objects.

## Secrets and data

- Never commit secrets, credentials, tokens, private keys, or production `.env` files.
- Inject runtime secrets from approved secret stores.
- Minimize personal/sensitive data in events and tasks.
- Redact tokens, passwords, cookies, authorization headers, raw provider data, and sensitive payloads from logs and traces.
- Define retention and deletion policy for identity, customer, payment, Chat, media, audit, backup, and event data before production.

## Supply chain

- Verify dependencies and images from official sources.
- Pin reproducibly and avoid unsupported releases or floating image tags.
- Run dependency and container scans with explicit severity gates, owners, and expiring exceptions.
- A delivery job must scan the exact local image it will tag and publish before
  registry authentication or any push; a scan from a different event, runner,
  or rebuilt image is not a publication gate.
- Use minimal CI permissions and immutable action references.
- Build non-root, minimal runtime images and retain artifact provenance when delivery is implemented.

## Required failure-policy decisions

- Redis loss during revocation, OTP, and rate limiting.
- Identity signing-key rotation and downstream cache failure.
- Provider webhook replay and signature failure.
- Object-storage authorization or scanning failure.
- CI scanner outage versus enforcement policy.
- Internal TLS and network trust boundaries for each environment.
