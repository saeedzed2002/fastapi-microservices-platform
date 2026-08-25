# ADR-007 — Restrict Redis to ephemeral platform state

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

The platform needs low-latency cache, rate limiting, temporary security state, presence, counters, and multi-pod WebSocket fan-out. These concerns do not justify moving durable domain truth out of PostgreSQL.

## Decision

Use Redis only for disposable or reconstructible state: caches, rate limits, OTP/session/revocation acceleration where appropriate, presence, WebSocket fan-out, temporary counters, and justified ephemeral locks.

Redis is never the sole durable store for carts, messages, orders, payments, inventory, media metadata, or security state whose loss would reactivate revoked credentials. Redis locks cannot be the only protection for durable invariants.

Define fail-open, fail-closed, or durable fallback behavior per feature before implementation.

## Consequences

### Positive

- Low-latency platform capabilities without transferring domain ownership.
- Cache and presence can be rebuilt after loss.
- Chat durability remains independent of realtime fan-out.

### Negative and risks

- Redis outage degrades several features simultaneously.
- Security-sensitive rate/revocation behavior requires explicit policy.
- Pub/Sub has no replay and can miss committed Chat notifications.

## Alternatives considered

- Redis as primary cart or Chat store: rejected because durable state would be lost or recovery-coupled.
- Database-only realtime fan-out: rejected initially because cross-pod delivery and presence need low-latency ephemeral coordination.

## Compatibility and migration

Redis is introduced feature by feature only after its fail-open, fail-closed, or durable fallback policy is documented. Key formats are namespaced and versioned where rolling deployments can overlap. Loss or flush of Redis must require no durable business-data migration.

## Validation

- Delete Redis state and verify no durable business data is lost.
- Chat messages remain queryable while fan-out is unavailable.
- Security-sensitive operations exhibit their documented degradation policy.

## Related material

- [Communication and consistency](../architecture/communication-and-consistency.md)
- [Realtime Chat diagram](../diagrams/realtime-chat.md)
- [Security baseline](../architecture/security-baseline.md)
