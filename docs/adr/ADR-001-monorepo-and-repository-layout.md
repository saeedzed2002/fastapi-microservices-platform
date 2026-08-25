# ADR-001 — Use a monorepo with independently deployable services

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

The platform contains many Python services plus shared contracts, infrastructure, end-to-end tests, diagrams, and delivery configuration. Cross-service contract changes need atomic review while services must remain independently understandable and deployable.

## Decision

Use the repository `fastapi-microservices-platform` as a monorepo. Place deployable bounded contexts under `services/`, canonical schemas under `contracts/`, small technical libraries under `libs/`, platform configuration under `infrastructure/`, and cross-service tests under `tests/e2e/`.

Monorepo location does not permit service-to-service source imports, shared databases, coordinated runtime releases, or shared domain entities.

## Consequences

### Positive

- Contract and consumer changes can be reviewed together.
- Tooling, documentation, CI policy, and local infrastructure are discoverable.
- Cross-service E2E tests can target one revision.

### Negative and risks

- Shared tooling can accidentally create lockstep releases.
- CI cost grows with the number of services.
- Broad shared libraries can turn the monorepo into a distributed monolith.

## Alternatives considered

- Repository per service: stronger repository isolation but high early coordination and contract-management cost.
- Modular monolith: simpler operations but does not meet the independently deployable microservices objective.

## Compatibility and migration

The repository is new, so no code migration is required. If a service is later split into another repository, its owned history, build, contracts, and delivery boundary must be migrated without introducing runtime source imports or a coordinated release requirement.

## Validation

- Every service builds and tests independently.
- A change detector runs affected services and dependents without skipping global contract gates.
- Repository checks forbid imports from another service and domain entities in `libs/`.

## Related material

- [Repository structure](../architecture/repository-structure.md)
- [Architecture overview](../architecture/overview.md)
