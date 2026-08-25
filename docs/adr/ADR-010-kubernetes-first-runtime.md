# ADR-010 — Design application workloads Kubernetes-first

- Status: `Accepted`
- Date: `2026-08-25`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

Kubernetes deployment is a later phase, but application assumptions made earlier determine whether workloads can scale, terminate, migrate, and recover safely.

## Decision

Design APIs as stateless, horizontally scalable workloads with external durable state, environment configuration, external secrets, immutable images, no durable local filesystem, and generally one application process per pod.

Every workload defines appropriate startup, liveness, readiness, graceful shutdown, resource request/limit, identity, and network behavior. Migrations run through controlled Jobs or delivery steps, never independently in every replica startup.

Use Docker Compose for local dependencies without coupling code to its topology. Stabilize raw Kubernetes resources before creating Helm charts.

## Consequences

### Positive

- Workloads can scale and restart without local-state loss.
- Probe, shutdown, migration, and resource behavior is designed rather than retrofitted.
- Local and production infrastructure can use different topologies behind the same configuration/contracts.

### Negative and risks

- Workers and consumers need workload-specific health and drain semantics.
- Readiness can cause outages if optional dependencies are treated as critical.
- Migration rollback and rolling compatibility require expand-migrate-contract changes.

## Alternatives considered

- Design for a single long-lived VM and retrofit Kubernetes later: rejected because filesystem, process, and shutdown assumptions would leak into application code.
- Helm from day one: rejected because templates would hide an unsettled deployment model.

## Compatibility and migration

Docker Compose remains the Phase 1 local topology. Phase 9 introduces explicit Kubernetes resources and controlled migration Jobs; Phase 10 templates the validated resources with Helm. Workload and schema changes use rolling-compatible expand-migrate-contract sequencing and retain a tested rollback path.

## Validation

- Termination tests prove intake stops and unfinished broker work is redelivered safely.
- Containers run without durable local writes and, unless required, without root.
- Readiness reflects only dependencies critical to the workload served.

## Related material

- [Deployment evolution](../diagrams/deployment-evolution.md)
- [Docker standards](../development/docker-standards.md)
- [CI/CD strategy](../development/ci-cd.md)
