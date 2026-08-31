# ADR-029: Helm packaging and controlled migrations

- Status: Accepted
- Date: 2026-08-31
- Owners: platform engineering
- Supersedes: none
- Superseded by: none

## Context

`ADR-027` established a reviewable raw Kubernetes workload model and `ADR-028`
proved that model in a disposable `Kind` cluster. Raw resources are still a
valuable baseline, but an environment operator needs a versioned, repeatable
release unit with explicit values for image digests, ingress inputs, and
runtime configuration. Copying and editing Kustomize overlays for each
environment would duplicate the deployment model and make release review
harder.

Migration ordering is non-negotiable: application workloads must not start
against an un-migrated schema. A single chart with ordinary resources cannot
run its migration Jobs before the `ConfigMap`, `Secret`, and ServiceAccount it
requires are present. A release design must retain the proven foundation,
migration, workload ordering without embedding environment secrets or
inventing an ingress/TLS implementation.

## Decision

Package the validated Phase 9 resources as two Helm `v2` API charts under
`infrastructure/helm/`:

1. `fastapi-platform-foundation` is installed first with
   `--create-namespace`. It owns the ServiceAccount, runtime ConfigMap,
   namespace resource policy, and default-deny ingress policy. It never
   creates the runtime Secret or registry credential.
2. `fastapi-platform` owns API Deployments and Services, workers, the media
   reaper CronJob, API PodDisruptionBudgets, and the optional public Ingress.
   Each service-owned Alembic Job is a `pre-install,pre-upgrade` Helm hook.
   Hooks retain current release evidence and use
   `before-hook-creation` to remove only the prior same-name migration Job.

The application chart requires one image value per executable service. Normal
delivery accepts only a lowercase SHA-256 digest and renders a digest-addressed
image. Mutable tags fail rendering unless the disposable conformance values
explicitly opt in; those values use only checkout-built local images with
`imagePullPolicy: Never`.

The conformance script now installs both charts into its temporary `Kind`
cluster. Test-only dependencies and deterministic non-production runtime
Secret remain Kustomize resources because they are a disposable test harness,
not a delivery topology. The script waits for Helm migration hooks and
workload rollout before the existing readiness and checkout E2E Jobs execute.

Helm `v4.2.4` is the selected client. CI downloads the official Linux archive,
verifies SHA-256
`c306b46f719b0a4da32d0f78ee21bf90ce8d602f15b22ab753f0674d1670a7f3`, then
lints and renders both charts on pull requests and installs them on trusted
main-line/manual conformance runs.

## Consequences

### Positive

- Environment release inputs are explicit chart values rather than copied
  manifests.
- The normal delivery path rejects mutable service tags and preserves the
  immutable-digest rule from `ADR-027`.
- Hook ordering makes migration completion an install/upgrade gate before API
  or worker workloads are created.
- CI now proves a Helm install in Kubernetes, not merely template rendering.

### Negative and risks

- Two Helm releases must be managed in order; the foundation release is a
  prerequisite for the application release.
- Helm hook Jobs are release lifecycle objects, so an operator must inspect a
  failed hook before retrying. An automatic Alembic downgrade remains
  prohibited.
- The conformance chart values intentionally permit local tags. They are not
  valid release values and must never be promoted to a target environment.
- Helm does not select an ingress controller, certificate issuer, cloud
  provider, secret manager, or autoscaling policy.

## Alternatives considered

- Keep Kustomize-only delivery: rejected because per-environment image and
  ingress substitutions remain manual and less auditable as release inputs.
- One chart with ordinary migration Jobs: rejected because it cannot guarantee
  migrations complete before application workloads start.
- One chart with hook-created foundation resources: rejected because it mixes
  long-lived foundation ownership into migration hook lifecycle and obscures
  the explicit operational boundary.
- Introduce a third-party chart for PostgreSQL, Kafka, RabbitMQ, Redis, or
  MinIO: rejected because production stateful-service topology remains
  environment-owned and no new deployment dependency is needed for this phase.

## Compatibility and migration

No public API, event schema, database ownership, or service runtime contract
changes. The Phase 9 raw resources remain as the reviewed baseline; new
environments use the Helm runbook. Existing Docker Compose development is
unchanged. A target environment creates the external runtime Secret and any
registry pull Secret outside Git, installs foundation, then upgrades the
application chart with compatible immutable image digests.

## Validation

- CI checksum-verifies Helm `v4.2.4`, lints and renders both charts with the
  non-production conformance values, and keeps raw Kustomize rendering checks.
- The trusted `Kind` job installs foundation, applies only disposable test
  dependencies and Secret inputs, installs the application chart, waits for
  migration hooks and workload rollout, then runs readiness and checkout E2E.
- Static tests ensure all service images, migrations, worker commands,
  restricted pod settings, and conformance tag controls are present.

## Related material

- [ADR-010](ADR-010-kubernetes-first-runtime.md)
- [ADR-027](ADR-027-raw-kubernetes-delivery-baseline.md)
- [ADR-028](ADR-028-kubernetes-conformance-ci.md)
- [Phase 10 plan](../development/phase-10-plan.md)
- [Helm delivery README](../../infrastructure/helm/README.md)
- [Kubernetes deployment runbook](../runbooks/kubernetes-deployment.md)
