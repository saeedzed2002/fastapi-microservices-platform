# Helm delivery charts

These Phase 10 charts package the validated Phase 9 Kubernetes resource
model. They are the controlled delivery path; the raw Kustomize resources
remain the reviewable baseline and the disposable conformance harness remains
test-only.

## Chart boundary

- `fastapi-platform-foundation/` owns the ServiceAccount, runtime ConfigMap,
  resource policy, and default-deny ingress NetworkPolicy. Install it with
  `--create-namespace`.
- `fastapi-platform/` owns migrations, APIs, workers, the cleanup CronJob,
  PodDisruptionBudgets, bounded API HorizontalPodAutoscalers, and the optional
  public Ingress. Its migrations are `pre-install` and `pre-upgrade` hooks, so
  Helm runs them before ordinary workload resources.

Neither chart creates `platform-runtime-secrets`, `ghcr-pull`, a certificate,
an ingress controller, or a stateful dependency. Those are environment-owned
inputs and must be supplied outside Git.

## Release procedure

Use checksum-verified `Helm v4.2.4` and a private release values file that
sets a published immutable digest for every service image. Install foundation
first:

```bash
helm upgrade --install platform-foundation infrastructure/helm/fastapi-platform-foundation \
  --namespace fastapi-platform --create-namespace \
  --values /secure/fastapi-platform-foundation-release-values.yaml \
  --wait --timeout 5m
```

Create the runtime and optional registry Secrets according to
`docs/runbooks/kubernetes-deployment.md`, then install the application chart:

```bash
helm upgrade --install fastapi-platform infrastructure/helm/fastapi-platform \
  --namespace fastapi-platform \
  --values /secure/fastapi-platform-release-values.yaml \
  --wait --wait-for-jobs --timeout 10m
```

The default application values intentionally contain no image digest, so a
normal render fails until the operator sets each digest. A tag is rejected
unless the test-only conformance values set `images.allowMutableTags=true`.
Do not copy that override into a delivery environment.

Before upgrade, use `helm diff` only if the environment has reviewed and
installed that plugin separately; this repository does not add plugins or
third-party chart dependencies. Always inspect migration-hook failures before
retrying. Roll back only to a schema-compatible, already validated digest.

## Validation

The `CI` workflow lints and renders both charts on every relevant run. Its
trusted `Kind` job installs both charts with the test-only values, waits for
migration hooks and workloads, then executes in-cluster readiness and the
checkout-to-invoice-to-email workflow.
