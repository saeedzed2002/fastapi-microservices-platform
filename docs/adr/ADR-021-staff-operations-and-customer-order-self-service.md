# ADR-021 — Staff operations, customer order self-service, and contact-email snapshots

- Status: Accepted
- Date: 2026-08-28
- Owners: identity-service, customer-service, order-service, platform architecture
- Supersedes: none
- Superseded by: none

## Context

The platform has a durable customer-support queue, but Identity previously had
no approved workflow to create a `support_agent` account. Customer profile APIs
also accepted any valid token rather than enforcing the `customer` role. Order
owns order history by boundary, but exposed only a known-order lookup, so a
storefront could not retrieve a customer's history and an administrator could
not perform a read-only operational review.

Customer OTP accounts begin without an email address. The checkout code
converted a missing contact email to the literal string `"None"`, which could
create an invalid invoice-delivery attempt. A contact email must be captured
before checkout when invoice email delivery is a product requirement.

## Decision

Customer-service owns a customer-controlled, normalized contact email in its
profile. The email is not an Identity credential, does not change the phone OTP
account, and is intentionally a contact snapshot rather than a verified
notification preference. Checkout requires that contact email and snapshots it
into the Order transaction. Existing literal `"None"` snapshots are migrated to
SQL `NULL`; no historical invoice event is replayed and no historical customer
profile is rewritten.

Order-service exposes cursor-paginated customer order history and a separate
read-only administrator review API. Customer tokens can query only their own
orders. `admin` tokens can review all order summaries and an order's immutable
purchase snapshot, state transitions, and invoice state. `support_agent` never
receives order-review permission. The increment adds no fulfilment, shipment,
refund, payment mutation, invoice download, or cross-service database access.

Identity keeps staff accounts and role claims. An active `admin` can create,
list, and activate or suspend accounts whose sole role is `support_agent`.
The public bootstrap CLI remains the only mechanism for the first `admin`.
Staff lifecycle changes are written to Identity's local authentication audit
table and suspension revokes refresh sessions. Existing access tokens remain
valid only until their existing short lifetime ends; downstream services never
read the Identity database.

Email/password login accepts active `admin` and `support_agent` accounts.
Identity adds a namespaced Redis failed-attempt limiter keyed by a SHA-256
digest of normalized email. It is separate from the edge's source-IP limit and
fails closed with `503` if Redis is unavailable. A threshold returns `429` with
`Retry-After`; successful staff authentication clears the failure counter
before a fresh refresh session is created. Customer login remains OTP-only.

## Consequences

- A customer must save an email contact before a checkout that requires invoice
  email. The mail is asynchronous after payment confirmation and invoice
  generation; it is not proof of an SMTP provider's final delivery.
- A support agent can sign in with email/password and claim support work, but
  cannot create staff accounts, administer other agents, or inspect orders.
- Administrator order APIs are read-only. Shipping, refund, payment, and
  fulfilment actions need their owning-service designs before they can be added.
- The Redis limiter intentionally stores no raw email address or password. A
  Redis outage blocks only staff password authentication, never customer OTP
  verification state or already-issued access tokens.
- Contact email validation uses direct `email-validator` `2.3.0`, already
  resolved in `uv.lock`. Its official `EmailStr` support handles syntax and
  normalization without a DNS lookup on every profile update. Customer-service
  declares it directly so its independently built image has the required
  runtime package.

## Alternatives considered

- Let Chat create or modify Identity roles: rejected because Chat does not own
  credentials or staff lifecycle.
- Let administrators query Customer or Identity databases from Order: rejected
  because Order already owns the required immutable order snapshot.
- Send invoice mail to a current Customer profile instead of the checkout
  snapshot: rejected because later profile edits must not alter a historical
  order's recipient.
- Rely only on the edge login limiter: rejected because edge state is IP-based,
  topology-dependent, and cannot replace service-owned authentication abuse
  control.
- Add mutable fulfilment actions to Order now: rejected because Shipping and
  refund ownership remain explicitly unscheduled architecture decisions.

## Compatibility and migration

All public APIs are additive except the corrected authorization rejection for
non-customer callers of Customer and checkout APIs. Existing email/password
customer accounts remain unable to use staff login. Existing administrator
accounts continue to log in. The Order migration adds query indexes and changes
only the invalid literal `"None"` email snapshot to `NULL`.

New OpenAPI artifacts define the Customer profile, Order query, and Identity
staff-management APIs. No Kafka event schema changes are required because a
customer contact update is local Customer state and Order already snapshots its
needed value synchronously before its local transaction.

## Validation

- Unit tests prove role gates, cursor parsing, missing-email checkout refusal,
  and the `"None"`-safe snapshot conversion.
- Identity tests prove staff provisioning/suspension audit behavior and the
  Redis failure/lockout policy without raw email keys.
- The Compose E2E flow saves a customer email, completes checkout, and waits
  for the resulting invoice email in Mailpit.
- Migration-head and complete local quality checks validate service schema
  ownership, contracts, formatting, types, and tests.

## Related material

- [Service boundaries](../architecture/service-boundaries.md)
- [Security baseline](../architecture/security-baseline.md)
- [Customer OTP decision](ADR-020-customer-phone-otp-authentication.md)
- [Chat support queue decision](ADR-019-chat-support-queue-assignment.md)
- [Invoice and notification runbook](../runbooks/invoice-notification.md)
