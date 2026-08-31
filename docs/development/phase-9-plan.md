# Phase 9 Plan — Kubernetes

## Outcome

Deliver raw, reviewable `Kustomize` resources that run the stateless platform
workloads on Kubernetes with controlled schema migration Jobs, resource and
availability controls, restricted pod security, deliberate network ingress,
and no committed runtime secret.

## Scope

- one restricted `fastapi-platform` namespace, service account, quota, limit
  range, and default-deny ingress policy;
- two-replica API deployments, services, startup/readiness/liveness probes,
  rolling-update policy, resource requests/limits, and disruption budgets;
- dedicated deployments for Celery workers and payment-expiry processing plus
  a single Media upload reaper `CronJob`;
- per-service migration `Job` resources, executed once before workloads;
- immutable image-digest placeholders, a runtime configuration `ConfigMap`,
  a non-applied secret example, a portable ingress contract, deployment
  runbook, and CI rendering validation;
- a disposable `Kind` conformance baseline that builds the checked-out service
  images, loads them into a temporary cluster, and proves the same foundation,
  migration, workload, readiness, checkout, inventory, invoice, and email
  sequence from inside the restricted application namespace. Phase 10 installs
  that stabilized sequence through Helm rather than applying the raw entries
  directly.
- migration sources and `alembic.ini` included in every database-owning
  service image so the migration Jobs can actually execute.

## Non-goals

- creating or operating a Kubernetes cluster, ingress controller, certificate
  issuer, external database, Kafka, RabbitMQ, Redis, object store, or secret
  manager;
- committing credentials, selecting a cloud provider, automatic production
  delivery, autoscaling policy, full observability stack, or Helm charts;
- changing business APIs, event schemas, database ownership, or service
  boundaries.

## Delivery sequence

1. Pin the delivery's service images to published `GHCR` digests and create
   the runtime and registry secrets outside Git.
2. Apply the foundation resources and verify the namespace policy.
3. Delete previous completed migration Jobs, apply the migration resources,
   and wait for every Job to complete before starting a new image revision.
4. Apply workload resources, wait for rollout and readiness, then run the
   service-owned readiness and in-cluster checkout E2E checks. A target
   environment owner separately verifies public `Ingress` routing.
5. Roll back only to an image compatible with the already-applied schema;
   database rollback is an explicit operator operation, never an automatic
   deployment side effect.

## Dependency selection

Phase 9 selects Kubernetes `v1.36.1`, `kubectl` `v1.36.1`, and `Kind`
`v0.32.0`. The latter's official stable release ships the exact pinned
`kindest/node:v1.36.1` image used by the conformance cluster. The job runs on
pushes to `main` and manual dispatches, rather than untrusted pull requests,
because it builds and starts the complete platform. It uses isolated,
deterministic test-only infrastructure credentials and never calls Zarinpal
or the SMS provider. This proves the repository deployment sequence, but not
target-environment ingress, real TLS, managed stateful-service networking, or
production credential delivery. The selection record and links are in
`docs/development/toolchain.md`.

Raw Kustomize resources are selected before Helm because the workload model,
external-state topology, ingress controller, and secret manager must stabilize
before template abstraction is useful. This preserves the boundary established
by `ADR-010` and is recorded more specifically in `ADR-027`.

Phase 10 packages this accepted raw baseline as Helm charts. The current
executable conformance path therefore installs those charts; this plan remains
the record of the raw-resource model that was stabilized first.
