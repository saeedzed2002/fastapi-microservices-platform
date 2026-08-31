# ADR-033: Bounded API horizontal pod autoscaling

- Status: Accepted
- Date: 2026-08-31
- Owners: platform engineering
- Supersedes: none
- Superseded by: none

## Context

`ADR-010` selects Kubernetes as the runtime model, and the delivery baseline
already declares explicit CPU requests, availability budgets, rolling-update
behavior, and immutable application images. Fixed API replica counts alone do
not respond to sustained demand, however. Claiming a scalable microservice
platform without a bounded controller policy would leave a material gap in the
deployment model.

The existing asynchronous workers are not equivalent to stateless HTTP APIs:
their safe throughput is governed by RabbitMQ queue depth, task latency,
provider limits, and idempotency. CPU-based `HPA` would be an unreliable proxy
for that work. The platform also has no target environment, cluster autoscaler,
or measured production load profile from which service-specific maxima can be
honestly derived.

Kubernetes documents `autoscaling/v2` as the stable HPA API. CPU utilization
is measured relative to explicit container CPU requests and requires the
resource Metrics API. The official `metrics-server v0.9.0` supports the
repository's Kubernetes `v1.36` baseline. It is used only in the disposable
Kind proof to establish that the HPA objects receive actual CPU samples.

## Decision

Every HTTP API Deployment receives an `autoscaling/v2`
`HorizontalPodAutoscaler` in both the raw Kustomize baseline and the Helm
application chart. The default policy is deliberately bounded:

- minimum `2` and maximum `4` replicas per API;
- target average CPU utilization `70%` of the explicit request;
- scale-up limited by either `2` Pods or `100%` per minute;
- scale-down limited to `25%` per minute after a `300` second stabilization
  window.

When autoscaling is enabled, the Helm Deployment starts at the configured HPA
minimum so the HPA is the sole steady-state owner of the replica count. The
namespace quota is expanded to cover HPA maxima, one zero-unavailable
rolling-update surge per API, and independently owned worker or migration
workloads.

Workers, CronJobs, migration Jobs, dependencies, and cluster nodes are outside
this decision. Queue-driven worker scaling requires separate queue-depth
metrics and a service-specific design. A target environment must provide a
working `metrics.k8s.io` API and enough node capacity; HPA cannot add nodes.

The conformance script downloads the official `metrics-server v0.9.0` release
manifest, verifies SHA-256
`1cec29a5267809306a2c6ec74a3e449abbb705b4a8beed0c8a1963910f72c79b`, loads
the exact image digest
`registry.k8s.io/metrics-server/metrics-server@sha256:d9862115e7c7881280d3d75ca26bda8ffc0fc213315979575bf23ce9826205c0`
into its disposable Kind node, and verifies the metrics API plus each HPA's
CPU sample. Its one-node values retain `1` as both the minimum and maximum;
this proves integration and metrics availability without pretending that the
test node supplies production capacity.

## Consequences

### Positive

- API scale policy, limits, and failure prerequisites are explicit and
  reviewable in both delivery representations.
- The conformance cluster proves the `metrics.k8s.io` data path and every HPA
  target after the real in-cluster checkout workflow is deployed.
- The resource quota cannot silently block the declared HPA ceiling or a
  zero-unavailable rolling update.

### Negative and risks

- A CPU signal is not a business-throughput SLO; each environment needs
  capacity evidence and may need a reviewed override.
- The temporary Kind metrics-server uses `--kubelet-insecure-tls` solely for
  Kind's self-signed kubelet certificate. That exception must not be copied to
  an environment cluster.
- This proof verifies HPA admission and current CPU metrics, not a synthetic
  scale-out under production traffic, multi-node scheduling, or node
  autoscaling.

## Alternatives considered

- Keep fixed replicas: rejected because it leaves the declared Kubernetes
  runtime without automatic API scaling.
- Apply CPU HPA to workers: rejected because queue depth and provider behavior
  are the relevant work signals.
- Introduce KEDA now: deferred because it adds a controller and external-metric
  design before a queue-scaling policy has been selected.
- Add a production metrics-server chart to this repository: rejected because
  cluster add-ons, node TLS, and control-plane policy are environment-owned.

## Compatibility and migration

No public API, event, database, or service ownership contract changes. Existing
environments that use the Helm chart must first confirm that
`metrics.k8s.io/v1beta1` is available and that cluster capacity supports the
configured maximum replicas. Do not manually set an API Deployment's replica
count while its HPA is enabled. A rollback that disables autoscaling restores
the Helm `api.replicas` value; it does not alter databases or image digests.

## Validation

- Static tests require all API targets, the stable HPA API, CPU request-based
  metrics, safe scale behavior, and matching Helm values.
- Raw Kustomize and Helm rendering validate the exact deployable objects.
- Disposable Kind conformance verifies the signed release manifest checksum,
  digest-pinned metrics-server image, available Metrics API, and current CPU
  utilization for every HPA target.
- Environment operators follow the autoscaling runbook and record capacity and
  load evidence before raising the maximum replica count.

## Related material

- [ADR-010](ADR-010-kubernetes-first-runtime.md)
- [ADR-027](ADR-027-raw-kubernetes-delivery-baseline.md)
- [ADR-028](ADR-028-kubernetes-conformance-ci.md)
- [ADR-029](ADR-029-helm-packaging-and-controlled-migrations.md)
- [Kubernetes autoscaling runbook](../runbooks/kubernetes-autoscaling.md)
- [Phase 15 plan](../development/phase-15-plan.md)
