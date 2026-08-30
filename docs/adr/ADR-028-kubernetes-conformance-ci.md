# ADR-028: Kubernetes conformance CI proof

- Status: Accepted
- Date: 2026-08-30
- Owners: platform engineering
- Supersedes: none
- Superseded by: none

## Context

`ADR-027` supplies raw Kubernetes resources, but rendering YAML does not prove
that application images start, service-owned migrations complete, or the
inter-service configuration works in a Kubernetes network. Treating an
unexecuted manifest as deployment evidence would be misleading in a portfolio
repository and unsafe as a release gate.

The production environment is intentionally not selected. Its registry
credentials, real provider credentials, ingress controller, TLS issuer, and
stateful-service topology must not be invented merely to exercise CI.

## Decision

On every push to `main` and manual workflow dispatch, create an isolated
`Kind v0.32.0` cluster with the exact digest-pinned Kubernetes `v1.36.1` node
image. Build all platform service images and the source-built MinIO image from
the checked-out commit, load them into that temporary node under
test-only `fastapi-platform/*:conformance` names, and never use those names in
production manifests.

The conformance overlay applies, in order:

1. the restricted application foundation plus an isolated dependency namespace;
2. all service-owned migration Jobs, waiting for completion;
3. API and worker workloads, waiting for rollout;
4. a non-root in-cluster Job that requests `/health/ready` from every API.

The test-only dependency namespace contains disposable PostgreSQL, Kafka,
RabbitMQ, Redis, MinIO, and Mailpit resources. Its credentials are deliberate
non-production test values. Zarinpal and SMS delivery stay disabled. On any
failure CI exports Kubernetes diagnostics, then deletes the cluster.

## Consequences

### Positive

- The repository proves the deployment sequence, image loading, migrations,
  service discovery, and API readiness on Kubernetes rather than claiming
  those properties from a successful render.
- CI uses exact pinned platform dependencies and does not expose provider or
  production credentials.
- Production raw manifests retain immutable image digests and remain separate
  from the disposable test overlay.

### Negative and risks

- The job builds and starts the full platform, so it runs on trusted main-line
  and manual workflows rather than on every untrusted pull request.
- It increases CI duration and uses a single-node test topology; it does not
  prove autoscaling, multi-zone scheduling, real TLS, public ingress, cloud
  IAM, or managed-stateful-service behavior.
- Local conformance tags are intentionally mutable within one disposable job;
  using them in a release manifest would violate `ADR-027`.

## Alternatives considered

- YAML rendering only: rejected because it cannot exercise migration Jobs or
  Kubernetes networking.
- Deploy to a public free-tier cluster: rejected because it adds cost,
  credential, TLS, and public attack-surface concerns without being as
  repeatable as CI.
- Run the complete cluster for every pull request: deferred because the
  existing PR quality, unit, integration, image-build, and scan gates already
  protect untrusted changes; the trusted main-line proof provides the
  reproducible deployment evidence.

## Compatibility and migration

No public API, event, database, or production deployment contract changes.
The conformance overlay is not an environment overlay and cannot be promoted.
It is deleted after every run.

## Validation

- Static policy tests ensure the overlay uses only local conformance images,
  disables registry pulls, preserves the production digest-only contract, and
  includes all owned migrations and API readiness checks.
- CI creates the cluster, waits for test dependencies, migrations, and
  Deployments, then runs the in-cluster health Job.
- Failure diagnostics include Kubernetes resources, events, and exported Kind
  node logs.

## Related material

- [ADR-027](ADR-027-raw-kubernetes-delivery-baseline.md)
- [Phase 9 plan](../development/phase-9-plan.md)
- [CI/CD strategy](../development/ci-cd.md)
- [Kubernetes conformance assets](../../infrastructure/kubernetes/conformance/README.md)
