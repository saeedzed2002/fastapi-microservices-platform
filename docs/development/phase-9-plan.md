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
   public ingress and service-owned smoke checks.
5. Roll back only to an image compatible with the already-applied schema;
   database rollback is an explicit operator operation, never an automatic
   deployment side effect.

## Dependency selection

Phase 9 selects Kubernetes `v1.37.0` and `kubectl` `v1.37.0`. The supported
Kubernetes release line and client-version skew policy were reviewed from the
official Kubernetes documentation on `2026-08-30`. The local rendering check
uses the available `kubectl v1.34.1`; it validates Kustomize structure only
and is not proof of compatibility with a target cluster. The selected release
record and links are in `docs/development/toolchain.md`.

Raw Kustomize resources are selected before Helm because the workload model,
external-state topology, ingress controller, and secret manager must stabilize
before template abstraction is useful. This preserves the boundary established
by `ADR-010` and is recorded more specifically in `ADR-027`.
