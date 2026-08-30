# ADR-027: Raw Kubernetes delivery baseline

- Status: Accepted
- Date: 2026-08-30
- Owners: platform engineering
- Supersedes: none
- Superseded by: none

## Context

`ADR-010` requires stateless, horizontally scalable workloads with controlled
migrations, but the repository did not yet contain executable Kubernetes
resources. A deployment design that starts migrations in every API replica or
uses mutable image tags would make rollout and recovery unsafe.

The platform has multiple independently deployed API and worker processes,
external durable state, public HTTP/WebSocket ingress, and secrets that must
not enter source control. The initial operating environment is not selected,
so its ingress controller, certificate provisioning, secret manager, and
external service DNS/CIDRs cannot be invented in repository YAML.

## Decision

Use raw `Kustomize` resources in Phase 9. They provide a restricted namespace,
non-root/read-only pod policy, resource controls, default-deny ingress,
availability budgets, stateless API deployments, dedicated worker deployments,
and a single scheduled Media reaper.

Every deployable image reference is an immutable digest placeholder. A release
operator replaces it only with the digest published by the validated `GHCR`
workflow. `platform-runtime-secrets` and `ghcr-pull` are required external
Secrets; the repository contains only a deliberately excluded template with
placeholders.

Schema migrations run once as named, controlled Jobs before a workload image
is rolled out. Migration scripts and `alembic.ini` are included in the
database-owning service images. Replica startup never runs migrations.

Ingress is a portable contract rather than a bundled controller: the target
cluster must provide its reviewed ingress class, TLS secret, public host, and
WebSocket/forwarded-header behavior. The namespace's default-deny policy is
intentionally ingress-only until the target environment supplies stable egress
destinations or an egress gateway; DNS, managed stateful services, and the
external payment provider cannot be safely restricted by guessed CIDRs.

## Consequences

### Positive

- Kubernetes rollout semantics, probes, security posture, capacity requests,
  and migration order are explicit and reviewable.
- Images cannot silently move under a deployment revision.
- A migration failure prevents rollout rather than being raced by replicas.
- A failed or abandoned Media upload remains cleaned up by exactly one
  scheduled workload.

### Negative and risks

- A real environment must supply ingress, TLS, secret management, registry
  credentials, external service endpoints, and an egress policy before public
  deployment.
- Static manifest validation cannot prove image pull, managed-service access,
  migration success, or ingress routing. `ADR-028` adds a disposable
  conformance cluster to prove the first three against test-only dependencies;
  it cannot prove a target environment's ingress or managed-service topology.
- Fixed-name migration Jobs must be deleted before a later release can create
  them again; the runbook makes this an explicit audited step.

## Alternatives considered

- Start migrations from every API container: rejected because concurrent
  replicas turn schema rollout into a race and hide failure state.
- Use `latest` or a mutable service tag: rejected because it breaks rollback
  provenance and makes migration/image compatibility unknowable.
- Add Helm now: rejected because templates would conceal unresolved deployment
  topology and environment choices. Helm is Phase 10 after the raw resources
  are proven stable.
- Default-deny all egress now: rejected because unknown managed-service and
  payment-provider destinations would cause accidental total outage.

## Compatibility and migration

No public API or event contract changes. Existing Compose development remains
supported. Delivery follows expand-migrate-contract: a release is pinned,
migration Jobs succeed, then compatible application workloads roll out. A
rollback selects a previously published compatible image and does not attempt
an automatic Alembic downgrade.

## Validation

- CI renders the production and conformance Kustomize entry points and checks
  the manifest policy.
- CI image builds prove migration sources are present in every owned image.
- A target cluster deployment follows `docs/runbooks/kubernetes-deployment.md`
  and records migration completion, rollout state, readiness, and ingress
  smoke results.

## Related material

- [ADR-010](ADR-010-kubernetes-first-runtime.md)
- [Phase 9 plan](../development/phase-9-plan.md)
- [Kubernetes deployment runbook](../runbooks/kubernetes-deployment.md)
- [ADR-028](ADR-028-kubernetes-conformance-ci.md)
