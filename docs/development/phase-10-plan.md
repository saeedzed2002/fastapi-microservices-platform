# Phase 10 Plan — Helm

## Outcome

Package the already-proven Kubernetes release sequence as reviewable Helm
charts. A target environment installs a foundation chart, supplies external
secrets, then installs or upgrades the application chart whose service-owned
migration hooks complete before compatible workloads roll out.

## Scope

- `Helm v4.2.4`, checksum-verified in CI and documented in the toolchain
  record;
- a foundation chart for the ServiceAccount, runtime ConfigMap, resource
  policy, and ingress NetworkPolicy;
- an application chart for APIs, workers, scheduled media cleanup,
  PodDisruptionBudgets, optional Ingress, and migration hooks;
- immutable digest-only production image rendering with a deliberately
  isolated local-tag conformance override;
- Helm lint/render checks on pull requests and a real chart installation in
  the trusted `Kind` conformance workflow;
- an operator runbook for controlled installation, upgrade, verification, and
  rollback.

## Non-goals

- selecting a cloud provider, ingress controller, certificate issuer, secret
  manager, external stateful-service topology, or autoscaling policy;
- committing runtime credentials, public hostnames, or release image digests;
- automatically deploying into a production environment;
- changing service APIs, event contracts, database schemas, or service
  boundaries;
- replacing the raw Phase 9 manifests as the reviewed workload baseline.

## Delivery sequence

1. Select a previously validated Git revision and its published immutable
   `GHCR` service digests.
2. Install or upgrade `fastapi-platform-foundation` with
   `--create-namespace`, then create the runtime Secret and optional registry
   pull Secret outside Git.
3. Run `helm upgrade --install` for `fastapi-platform` with `--wait` and
   `--wait-for-jobs`. Its migration hooks must complete before workload
   resources are applied.
4. Validate rollout, migration evidence, service readiness, authenticated
   WebSocket behavior, public ingress/TLS, and bounded business smoke checks.
5. On failure, preserve diagnostics and select a previously validated,
   schema-compatible immutable digest. Never issue automatic Alembic downgrade.

## Dependency selection

Helm `v4.2.4` is the official stable release selected on `2026-08-31`. Its
official changelog reports Kubernetes `v1.36` support, compatible with the
existing `Kind` and `kubectl` target. CI downloads the official Linux archive
from `get.helm.sh` and verifies SHA-256
`c306b46f719b0a4da32d0f78ee21bf90ce8d602f15b22ab753f0674d1670a7f3` before
use. The selection evidence is recorded in
[the toolchain record](toolchain.md).
