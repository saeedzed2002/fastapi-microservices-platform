# ADR-031 — Staff password reset and device-session lifecycle

- Status: `Accepted`
- Date: `2026-08-31`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

Customers use phone OTP and have no password credential to recover. Existing
`admin` users authenticate with a password, but previously had neither a safe
recovery mechanism nor a way to inspect and revoke device sessions. Refresh
rotation existed, but reuse of an already-revoked token did not contain the
whole token family.

## Decision

Identity exposes password recovery only for active `admin` users with a
password hash. The request endpoint always returns the same `202` response for
an eligible, unknown, inactive, or customer account. A Redis cooldown keyed by
a hash of the normalized email rate-limits requests without retaining the raw
email in the key.

Identity stores a SHA-256 hash of a one-time reset token and its expiry in its
own PostgreSQL database. The raw token is held only in a short-lived namespaced
Identity Redis delivery key. After the database transaction commits, Identity
asks Notification over the existing authenticated private channel to create a
durable email-delivery intent. Notification persists only the delivery ID and
recipient; its Celery task retrieves the raw token immediately before SMTP
delivery. Raw reset tokens never enter PostgreSQL, Kafka, RabbitMQ, Celery
payloads, logs, traces, or public responses.

Reset confirmation changes the Argon2id password, consumes the reset request,
revokes every active refresh session for that user, removes the temporary
delivery key, and writes an authentication audit event in one Identity
transaction. If the durable Notification handoff cannot be confirmed, Identity
consumes the request and removes the raw key rather than leaving an undelivered
credential active.

Refresh sessions now retain a bounded user-agent string, an HMAC-SHA256 hash of
the observed peer address, and a last-used timestamp. The public session API
lets the authenticated user list active sessions, revoke one owned session, or
revoke all active sessions. It deliberately does not expose a raw IP address or
claim which session is "current"; an access token does not identify its refresh
session.

On refresh, a token whose stored hash matches an already-revoked session is
treated as verified reuse. Identity revokes every still-active session in that
family before returning the same generic `401` response. A malformed token,
unknown session, hash mismatch, or ordinary expired token cannot revoke another
family.

## Consequences

- The delivery path is durable and retryable, but SMTP acceptance is not proof
  that a human received the email.
- The user can safely recover a compromised staff account even if an old
  refresh token remains on another device.
- Password reset is intentionally unavailable for customers: customer sign-in
  and recovery remain phone-OTP concerns.
- A Redis outage fails reset creation and raw-token retrieval closed. Existing
  access tokens remain valid until their short expiry; active refresh sessions
  can still be revoked from Identity PostgreSQL.
- The IP digest is security metadata, not a location or device-fingerprint
  claim. No raw address is stored or returned.

## Alternatives considered

- Put the raw token in a Kafka event or Celery payload: rejected because the
  token would become durable or broadly observable.
- Send SMTP synchronously from Identity: rejected because provider work belongs
  to Notification and must not run inside the request transaction.
- Revoke every session whenever any invalid refresh token is submitted:
  rejected because arbitrary token strings could log out other users.
- Add a general staff role: rejected because the accepted two-role model is
  `customer` and `admin`; this feature follows that existing policy.

## Validation

- Unit tests cover reset-token delivery state, cooldown, cleanup, and raw-token
  containment.
- API-schema tests verify the public reset and session routes and exclude the
  private raw-token endpoint.
- Integration validation covers durable Notification task intent creation and
  worker retrieval without persisting a raw reset token.

## Related material

- [Identity token lifecycle](ADR-011-identity-token-and-account-lifecycle.md)
- [Customer OTP authentication](ADR-020-customer-phone-otp-authentication.md)
- [Security baseline](../architecture/security-baseline.md)
- [Identity boundary](../architecture/service-boundaries.md)
- [Staff password reset and sessions runbook](../runbooks/staff-password-reset-and-sessions.md)
