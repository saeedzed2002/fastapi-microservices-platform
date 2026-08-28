# ADR-020 — Customer phone OTP authentication and asynchronous SMS delivery

- Status: `Accepted`
- Date: `2026-08-28`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

The storefront authenticates ordinary customers by Iranian mobile number and a
one-time code. Administrators retain the established email/password path. A
customer code is security-sensitive, short-lived, and must not appear in Kafka,
PostgreSQL, logs, or a client response. SMS delivery is a retryable provider
operation and must not run in an HTTP handler.

## Decision

Identity normalizes customer phones to `989xxxxxxxxx`, generates six-digit
codes, and stores only a code hash plus attempt/cooldown/rate-limit state in
namespaced Redis keys. Redis failure is fail-closed for request and verification:
no code is issued or accepted while that security state is unavailable.

Identity requests a private Notification delivery API over an authenticated
internal connection. Notification stores delivery metadata and a `TaskIntent`
in one local transaction, then its dispatcher publishes a confirmed Celery task
to `notification.sms`. The task contains only a delivery ID. The SMS worker
retrieves the short-lived code from Identity over the same internal-authenticated
channel immediately before calling the provider. Consequently, raw OTP values
are limited to Identity's temporary Redis state and in-memory internal requests;
they are absent from Notification PostgreSQL, RabbitMQ, Celery payloads, Kafka,
provider errors, and logs.

The initial provider adapter uses the `SMS.ir` Bulk API and a configured
services-enabled line because the current panel workflow has no approved
template. The adapter records provider acceptance, not handset delivery. A
future template-based `Verify` adapter is a compatible replacement when a
template ID is provisioned.

Successful first verification creates a customer Identity user and the
`identity.user_registered.v2` outbox record in one transaction. The new event
contains only the user ID, normalized phone, and roles. Customer-service
continues accepting deprecated `v1` email events during migration.

`POST /api/v1/auth/register` now returns `410 Gone`; it cannot create a
password-based customer. `POST /api/v1/auth/login` permits only an existing
`admin` role with an email and password.

## Consequences

- SMS provider outage returns a safe `503`; Identity deletes the provisional
  challenge so an unsent code cannot authenticate.
- Broker retry after a provider-acceptance/database-update crash may issue the
  same code more than once. This is safe and expected at-least-once external
  delivery; clients deduplicate by phone and code lifetime.
- The configured SMS line must be services-enabled. Otherwise a recipient on a
  carrier block list can fail to receive an OTP even when the provider accepts
  the Bulk request.
- Existing customer email/password accounts cannot use the public login endpoint
  after rollout. Existing administrators remain able to log in if their role,
  email, and password hash are present.

## Alternatives considered

- Calling `SMS.ir` from Identity's HTTP handler: rejected because external SMS
  is directed background work owned by Notification.
- Storing raw OTP text in Notification delivery records or Celery payloads:
  rejected because it unnecessarily widens durable/broker exposure.
- Publishing an OTP Kafka event: rejected because OTP values are commands and
  sensitive temporary state, not durable domain facts.
- Requiring an `SMS.ir` template before this local rollout: deferred. The
  provider's Verify API remains the preferred future option for universal
  services delivery.

## Compatibility and migration

`identity.user_registered.v1` remains consumable while existing email-password
customer projections drain. New customer creation publishes only
`identity.user_registered.v2`; Customer-service accepts both versions and uses
the Identity user ID for idempotency. The public registration endpoint remains
at its existing path but returns `410 Gone`, which is an intentional breaking
product-policy change rather than a silent password fallback. Existing
administrator users are compatible only when they retain an `admin` role,
email, and password hash.

The first local administrator is provisioned with an interactive, non-public
Identity CLI. It receives an `admin` role, prompts for the password twice, and
refuses to overwrite an existing email. This intentionally does not create a
general role-management API or bypass audited administrator lifecycle policy.

The private Identity/Notification endpoints are deployment-internal and are
not part of the external OpenAPI contract. They require the same rotatable
environment secret at both ends; a rollout with a missing or mismatched secret
fails closed with `503` or `401` rather than emitting an OTP.

## Validation

- Unit tests cover phone normalization, cooldown, verification attempts, and
  administrator/customer separation.
- Integration tests cover the authenticated Identity-to-Notification handoff,
  task intent, worker idempotency, and provider result parsing without a real
  provider credential.
- Local operator validation uses the provider sandbox or a services-enabled test
  line after secrets are supplied through the ignored root `.env`.

## Related material

- [Identity boundary](../architecture/service-boundaries.md)
- [Security baseline](../architecture/security-baseline.md)
- [RabbitMQ and Celery decision](ADR-006-rabbitmq-celery-tasks.md)
- [Redis ephemeral-state decision](ADR-007-redis-ephemeral-state.md)
- [SMS OTP runbook](../runbooks/sms-otp.md)
