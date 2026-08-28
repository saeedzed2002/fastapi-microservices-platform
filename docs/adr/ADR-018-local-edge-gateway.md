# ADR-018 — Local edge gateway and public API topology

- Status: `Accepted`
- Date: `2026-08-28`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

The architecture requires an edge layer for local development and Kubernetes.
Before this decision, Docker Compose published every API service directly on a
different host port. That exposed topology to clients, contradicted the system
context documentation, bypassed edge TLS and request controls, and left the
Chat WebSocket without a single public endpoint.

The edge is a transport boundary, not a replacement for service authorization.
Each service must continue to authenticate requests and enforce its own
resource and business policy. Object bytes use presigned S3 requests whose
canonical URI and signature must remain unchanged.

## Decision

Docker Compose runs one non-root, read-only Nginx edge container. It exposes
`https://localhost` as the canonical local API address and redirects
ordinary HTTP requests from `http://localhost`. The service route
prefixes are preserved exactly:

- `/api/v1/auth/` -> Identity
- `/api/v1/customers/` -> Customer
- `/api/v1/catalog/` -> Catalog
- `/api/v1/media/` -> Media
- `/api/v1/inventory/` -> Inventory
- `/api/v1/carts/` -> Cart
- `/api/v1/orders/` -> Order
- `/api/v1/chat/` -> Chat
- `/api/v1/reference` -> Reference

Internal paths are denied at the edge. Payment and Notification currently have
no public versioned HTTP contract and are intentionally not given invented
routes. The exact Chat WebSocket route `/api/v1/chat/ws` forwards HTTP
upgrade headers and disables proxy buffering.

For local Docker Compose development only, the edge provides an index at
`/docs/` and rewrites each service's stock FastAPI Swagger page under
`/docs/<service>`. Each page reads only its matching
`/docs/<service>/openapi.json` document. These documentation paths are not
public API contracts and must not be added to production ingress or edge
configuration.

The selected image is the official stable
`nginx:1.30.4-alpine@sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46`.
Nginx terminates local TLS using a developer-generated, untracked,
self-signed certificate. It also adds edge request headers, permits
`TLSv1.2` and `TLSv1.3`, applies a general source-IP limit of `30r/s`,
and applies stricter limits to login, future OTP/password-reset routes,
uploads, and WebSocket upgrades.

All API service host-port publications are removed. PostgreSQL, Kafka,
RabbitMQ, Redis, Mailpit, and MinIO keep their explicit local development or
operations ports. In particular, MinIO remains direct because routing
presigned object-byte requests under an edge prefix would invalidate S3
SigV4 canonical-request signatures.

## Consequences

### Positive

- Clients use one versioned API origin rather than service-specific ports.
- Local development exercises TLS, route mapping, headers, basic limits, and
  WebSocket forwarding before Kubernetes.
- Developers can inspect every service's local OpenAPI contract without
  reopening direct service host ports.
- Internal service routes and direct API host ports are not client entry points.
- The edge is reproducibly pinned and its image is scanned in pull-request CI.

### Negative and risks

- The local certificate is intentionally untrusted until a developer imports it
  into a local trust store; E2E clients disable certificate verification only
  for this local self-signed endpoint.
- Nginx source-IP limits are per edge instance and are not a distributed
  security control. Service-owned Redis-backed limits remain mandatory.
- The edge readiness endpoint proves edge-process availability, not universal
  domain-service health.
- Kubernetes must configure trusted proxy source handling deliberately before
  using forwarded client-address headers.

## Alternatives considered

- Direct service ports: rejected because clients learn deployment topology and
  bypass the required edge controls.
- Traefik with Docker socket discovery: rejected because this platform has a
  stable explicit route map and the socket privilege is unnecessary.
- Gateway-only authentication and authorization: rejected because it cannot
  enforce service-owned resource policy and would centralize business rules.
- Proxying MinIO through a path prefix: rejected because it breaks presigned
  S3 request signatures.

## Compatibility and migration

Existing public URI prefixes and service contracts do not change. Local callers
must switch to `https://localhost` and generate a certificate with
`pwsh -NoProfile -File scripts/new_local_edge_certificate.ps1` before
starting Compose. HTTP callers receive a `308` redirect. The local
certificate and private key are ignored by Git and must never be promoted to a
production deployment.

Kubernetes ingress implementation remains a later deployment concern, but it
must preserve these prefixes, WebSocket upgrades, TLS termination, header
policy, and the distinction between edge routing and service authorization.

## Validation

- Validate the Nginx configuration with `nginx -t` in the pinned container.
- Validate the Compose model and start the complete local platform.
- Prove HTTPS routing, security headers, HTTP redirect, internal-route denial,
  sensitive-route `429` behavior, and absence of the former Identity host
  port.
- Run checkout, invoice, notification, media, and Chat WebSocket E2E workflows
  through the edge.

## Related material

- [Architecture overview](../architecture/overview.md)
- [Security baseline](../architecture/security-baseline.md)
- [Edge gateway runbook](../runbooks/edge-gateway.md)
- [Toolchain record](../development/toolchain.md)
- [Testing strategy](../development/testing-strategy.md)
