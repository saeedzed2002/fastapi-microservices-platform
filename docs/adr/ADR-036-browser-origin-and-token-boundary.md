# ADR-036: Secure runtime defaults and browser token boundary

- Status: Accepted
- Date: 2026-08-31
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

The repository exposes API contracts only; it does not include a browser
frontend. Authentication endpoints currently return `TokenResponse` as JSON,
and API clients present the access token as a bearer credential. Neither the
FastAPI services nor the Nginx edge emit CORS policy headers or issue
authentication cookies.

Several service settings use explicit, public local-development values so the
Compose topology can start without an external secret manager. The settings
previously accepted those values in every environment. A production or
conformance process could therefore start with a known JWT, HMAC, internal
access-proof, object-storage, or RabbitMQ credential when an operator omitted
an override.

## Decision

Known local-development credentials are permitted only when a service setting
has `environment=local`. Every service that owns such a credential calls the
shared runtime guard while validating `Settings`. Any other environment fails
configuration validation before the application process can create its FastAPI
application or start a worker. The failure names unsafe setting fields but
never prints their values.

The current API remains browser-origin restrictive by default: no service
enables CORS middleware and the edge emits no CORS response headers. The
platform does not issue `HttpOnly` authentication cookies. The existing JSON
token response and bearer-token client contract remain unchanged.

Before adding a browser frontend, an approved architecture change must define
the exact allowed origins, methods, headers, credential behavior, token
storage, content-security policy, refresh flow, and logout/revocation behavior.
A cookie-based design must specify `HttpOnly`, `Secure`, `SameSite`, path and
domain scope, plus an explicit CSRF defense. A bearer-token design must define
the browser XSS containment and client-side storage policy. No wildcard CORS
origin or credential policy is allowed as a temporary shortcut.

## Consequences

### Positive

- An omitted non-local secret override fails loudly before the affected API or
  asynchronous worker can accept traffic.
- Local Compose keeps its frictionless, explicitly marked development
  credentials without weakening Kubernetes or other non-local environments.
- Browser security behavior is an explicit API boundary instead of an
  accidental absence of CORS or cookie behavior.

### Negative and risks

- A non-local deployment with incomplete secret injection now fails at startup;
  this is intentional and requires an operator to correct the release input.
- JSON token responses require every current non-browser client to protect its
  bearer and refresh material. They do not provide browser-specific XSS
  containment by themselves.
- A future browser client requires additional threat-model work rather than
  merely adding CORS headers.

## Alternatives considered

- Documentation-only reminders for secret overrides: rejected because they
  fail silently when an operator overlooks them.
- Enable permissive CORS now: rejected because there is no browser client,
  origin inventory, or credential policy to justify it.
- Switch immediately to `HttpOnly` cookies: rejected because it would change
  the established API-client contract and requires a complete CSRF and browser
  session design.

## Compatibility and migration

No API, event, database, or token-schema change occurs. Local Compose retains
`environment=local` and its development-only values. Every Kubernetes and
other non-local release must inject the required credential values through its
approved secret-delivery mechanism before the process starts. Existing
non-local releases that relied on a known default must replace it and roll out
normally; no data migration is required.

## Validation

- Unit tests cover the shared guard, including the no-value-leak error path.
- Parameterized tests instantiate every affected service configuration with
  every known unsafe value and require rejection outside `local`.
- Static tests keep CORS middleware and edge CORS headers absent until an
  approved browser-origin change updates this ADR and its tests.
- The Kubernetes conformance Secret supplies non-default values for each
  affected setting, proving the delivery topology remains bootable.

## Related material

- [Identity token and account lifecycle](ADR-011-identity-token-and-account-lifecycle.md)
- [Security baseline](../architecture/security-baseline.md)
- [Kubernetes deployment runbook](../runbooks/kubernetes-deployment.md)
- [Runtime Secret inventory](../../infrastructure/kubernetes/foundation/runtime-secrets.example.yaml)
