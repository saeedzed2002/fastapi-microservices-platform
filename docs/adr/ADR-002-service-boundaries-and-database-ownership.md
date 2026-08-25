# ADR-002 — Enforce bounded contexts and database ownership

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

Multiple applications sharing tables are not independently deployable services. Direct cross-service queries bypass invariants, couple migrations, and hide runtime dependencies.

## Decision

Every service owns its durable data, schema, credentials, migrations, transaction boundaries, and business invariants. No service queries or mutates another service's database.

One physical PostgreSQL instance may host several logical service databases locally. Ownership is still enforced through separate databases or schemas, users, grants, migration histories, and code boundaries.

Cross-service information flows through versioned REST APIs or Kafka events and local projections.

## Consequences

### Positive

- Services evolve schemas and deploy independently.
- Business invariants remain under one authority.
- Integration dependencies become explicit and observable.

### Negative and risks

- Cross-service joins are unavailable.
- Data is duplicated in snapshots and projections.
- Workflows become eventually consistent and require recovery behavior.

## Alternatives considered

- Shared database/schema: rejected because it creates hidden coupling and shared release boundaries.
- Read-only foreign-table access: rejected because schema and availability coupling remains.

## Compatibility and migration

Phase 1 must create separate logical ownership, credentials, grants, and migration histories even if one local PostgreSQL instance hosts them. Any later extraction from a shared physical instance is an infrastructure migration only; service contracts and ownership do not change.

## Validation

- Database credentials cannot access another service's objects.
- Migrations execute per service.
- Contract and E2E tests cover required integration paths.

## Related material

- [Service boundaries](../architecture/service-boundaries.md)
- [Service container view](../diagrams/service-container.md)
