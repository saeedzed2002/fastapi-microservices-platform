# ADR-011 — Identity tokens and account lifecycle

- Status: Accepted
- Date: 2026-08-25
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

The first business services need a shared authentication contract without sharing
identity domain tables or forcing customer-service to own credential state.
Registration also needs a durable cross-service handoff so a customer profile can
be provisioned after the identity transaction commits.

## Decision

Identity-service owns users, password hashes, refresh sessions, and authentication
state. Passwords use Argon2id. Access tokens are short-lived JWTs signed with
HS256 using an environment-provided secret of at least 32 bytes, with explicit
issuer and audience claims. The initial access lifetime is 15 minutes. Consumers
require the issued-at claim and accept it at most two seconds in the future to
tolerate bounded clock skew; expiration remains strict.

Refresh tokens are opaque values. Only a SHA-256 hash is stored. Every refresh
rotates the session token while retaining its family identifier; logout revokes
the presented session. Access-token revocation is bounded by the short lifetime
in this phase. A Redis denylist is deferred until the platform requires
immediate access revocation.

Registration writes the user and an identity.user_registered.v1 outbox record in
one local transaction. An outbox publisher sends the canonical event envelope to
Kafka with the aggregate ID as the message key. Customer-service consumes the
event and idempotently provisions its own profile row.

The platform-auth library contains only technical JWT claim and validation
primitives. It does not contain User, Customer, or any other business model.

## Consequences

- Identity credentials remain isolated from customer profile data.
- Kafka outage after registration leaves a durable pending outbox record.
- The first deployment uses an explicit shared secret between identity-service
  and consumers; production asymmetric signing and JWKS rotation require a
  separate approved ADR.
- Customer provisioning is eventually consistent and must tolerate duplicate
  delivery.

## Alternatives considered

- Customer-service owning credentials: rejected because it violates bounded
  context ownership.
- Long-lived self-contained access tokens: rejected because compromise impact is
  unnecessarily large.
- Publishing directly after commit: rejected because a broker outage would lose
  the identity fact.

## Validation

- Argon2id hashing and JWT round trips are unit tested.
- Event payload and envelope examples are cataloged under contracts/events.
- The outbox publisher has a deterministic envelope builder and idempotent
  publish marking.

## Compatibility and migration

The initial deployment keeps HS256 and one issuer/audience contract. Before
production federation or multi-tenant operation, a compatibility review must
define asymmetric keys, JWKS publication, rotation, and dual-validation
rollout. Event consumers must continue accepting the current event version
until a separately versioned replacement is deployed.

## Related material

- Phase 2 plan: docs/development/phase-2-plan.md
- Identity payload contract: contracts/events/identity.user_registered.v1.schema.json
- Outbox and event envelope ADR: docs/adr/ADR-005-outbox-inbox-and-idempotency.md
