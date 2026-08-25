# ADR-009 — Version APIs, events, and services independently

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

HTTP clients, Kafka consumers, and deployment systems evolve on different timelines. Treating one version number as all three creates unnecessary breaking changes and coordinated releases.

## Decision

- External HTTP APIs start under `/api/v1`.
- Event types carry schema versions such as `order.created.v1`.
- Deployable services use independent semantic versions and immutable Git-SHA image tags/digests.

A service release can change without changing its API or event version. A breaking event change creates a new event version; existing schemas are not destructively modified. Topic migration is governed separately from event schema versioning.

## Consequences

### Positive

- Internal releases do not force public contract churn.
- Old consumers and retained events remain interpretable.
- Independent service rollback and rollout are visible.

### Negative and risks

- Multiple versions may coexist during migration.
- Documentation and contract catalogues require disciplined maintenance.
- Topic suffixes and event suffixes can be confused without a migration policy.

## Alternatives considered

- One platform-wide release version: rejected because it creates lockstep deployment and contract churn.
- Unversioned APIs or events: rejected because retained messages and independent clients must remain interpretable.
- Topic names as the only event version: rejected because topic lifecycle and payload-schema compatibility are separate concerns.

## Compatibility and migration

Old and new API or event versions coexist for a documented consumer migration window. A breaking event change adds a new immutable schema and event type instead of rewriting retained history. Deprecation and removal require known-consumer evidence, replay analysis, contract-catalog status changes, and rollback compatibility.

## Validation

- CI compares OpenAPI and event contracts for breaking changes.
- Images carry immutable revision identity.
- Service documentation lists API, produced/consumed event, and image versions separately.

## Related material

- [Contract catalogue](../../contracts/README.md)
- [Event contracts](../../contracts/events/README.md)
- [Open questions](../architecture/open-questions.md)
