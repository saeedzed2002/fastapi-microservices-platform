# Kubernetes deployment

## Scope and safety boundary

This runbook deploys the Phase 10 Helm charts. The Phase 9 raw resources remain
the reviewed baseline but are not the environment delivery command. This runbook does not create a cluster,
an ingress controller, TLS issuer, secret manager, cluster metrics provider,
node autoscaler, or managed stateful service.
Do not treat a successful `helm upgrade` as proof of a target environment's
external dependencies or public routing. The disposable CI conformance job
does prove foundation-chart installation, migration hooks, workloads, and
in-cluster business behavior against local test dependencies; it does not
replace this environment-specific runbook.

Use a Kubernetes `v1.36.1` control plane, a supported `kubectl` client, and
checksum-verified `Helm v4.2.4`. The release layout is:

1. `infrastructure/helm/fastapi-platform-foundation`
2. externally supplied runtime and optional registry Secrets
3. `infrastructure/helm/fastapi-platform`

Never bypass the application chart's migration hooks or allow API replicas to
run their own migrations.

## Required environment inputs

Before any apply, an environment owner must provide:

- a reviewed Kubernetes ingress controller and its actual `IngressClass`;
- the actual public hostname and a TLS secret named `platform-public-tls`;
- DNS, TLS, and trusted-proxy policy compatible with HTTP and WebSockets;
- reachable external PostgreSQL databases, Kafka, RabbitMQ, Redis, object
  storage, SMTP/SMS configuration where enabled, and the payment-provider
  callback public URL;
- a secret manager or equivalent audited secret-delivery method;
- a healthy `metrics.k8s.io/v1beta1` implementation and enough node capacity
  for the approved API HPA maximum; the chart does not install metrics-server
  or a cluster autoscaler;
- private-registry pull credentials if `GHCR` packages are not public;
- an explicit egress-policy design for those real dependency endpoints.

The optional chart ingress is disabled by default. Before deployment, create a
private release values file that sets its ingress class, host, TLS secret, and
`PAYMENT_ZARINPAL_CALLBACK_URL` in the foundation values file. Do not commit
environment hostnames or credentials to the shared repository.

## Release images

The application chart has no default image digest and intentionally fails to
render until a private release values file sets every service's published
immutable digest from one validated `publish-ghcr` workflow. The same digest
must be used by its API, event worker, Celery worker, and migration hook. The
foundation configuration disables asynchronous-loop flags in API Pods; each
event-worker Deployment overrides only the flags it owns. Do not manually
enable those flags in API release values, because API `HPA` and rolling updates
would then alter Kafka consumer ownership and task-dispatch throughput.

Verify that every rendered image is digest-addressed before applying:

```bash
helm template fastapi-platform infrastructure/helm/fastapi-platform \
  --namespace fastapi-platform \
  --values /secure/fastapi-platform-release-values.yaml | \
  grep -E 'image: .*@sha256:[0-9a-f]{64}' >/dev/null
```

The release image and schema must be rolling compatible. An application
rollback selects an older compatible image; it does not execute automatic
Alembic downgrade.

## Secrets

Create `platform-runtime-secrets` in namespace `fastapi-platform` from the
approved secret manager. Its required key inventory is documented in
`infrastructure/kubernetes/foundation/runtime-secrets.example.yaml`; that file
is not an applyable secret and must never receive real values.

Create `ghcr-pull` only when the selected `GHCR` packages require it. Use an
audited pull-only token, not an administrator credential. Confirm both Secrets
exist without printing their data:

```bash
kubectl -n fastapi-platform get secret platform-runtime-secrets
kubectl -n fastapi-platform get secret ghcr-pull
```

If the ingress controller runs in another namespace, grant it access through
the explicit namespace label used by the namespace policy:

```bash
kubectl label namespace <ingress-controller-namespace> platform.fastapi.io/allow-ingress=true
```

## Deployment procedure

Lint and render the exact release values locally first:

```bash
helm lint infrastructure/helm/fastapi-platform-foundation --strict \
  --values /secure/fastapi-platform-foundation-release-values.yaml
helm lint infrastructure/helm/fastapi-platform --strict \
  --values /secure/fastapi-platform-release-values.yaml
helm template platform-foundation infrastructure/helm/fastapi-platform-foundation \
  --namespace fastapi-platform \
  --values /secure/fastapi-platform-foundation-release-values.yaml >/dev/null
helm template fastapi-platform infrastructure/helm/fastapi-platform \
  --namespace fastapi-platform \
  --values /secure/fastapi-platform-release-values.yaml >/dev/null
```

Install the foundation chart and verify its policy objects:

```bash
helm upgrade --install platform-foundation infrastructure/helm/fastapi-platform-foundation \
  --namespace fastapi-platform --create-namespace \
  --values /secure/fastapi-platform-foundation-release-values.yaml \
  --wait --timeout 5m
kubectl get namespace fastapi-platform
kubectl -n fastapi-platform get configmap platform-runtime-config
kubectl -n fastapi-platform get networkpolicy
```

Create the external runtime and optional registry Secrets only after foundation
has created the namespace. Then install or upgrade the application chart. Its
fixed-name migration hooks delete only a prior hook with the same name, run
before ordinary workload resources, and remain available for current release
evidence:

```bash
helm upgrade --install fastapi-platform infrastructure/helm/fastapi-platform \
  --namespace fastapi-platform \
  --values /secure/fastapi-platform-release-values.yaml \
  --wait --wait-for-jobs --timeout 10m
kubectl -n fastapi-platform get jobs -l platform.fastapi.io/workload=migration
```

If any migration fails, stop. Inspect only the failed Job logs, correct the
release values or operational dependency, then rerun the same Helm command.
Do not start or scale workloads to bypass migration failure:

```bash
kubectl -n fastapi-platform get jobs -l platform.fastapi.io/workload=migration
kubectl -n fastapi-platform logs job/<failed-migration-job>
```

Only after Helm reports success, confirm its workload rollout and HPA metric
availability. Do not use `kubectl scale` for an HPA-managed API Deployment:
the controller owns its replica count.

```bash
kubectl -n fastapi-platform rollout status deployment --timeout=10m
kubectl -n fastapi-platform get pods,services,pdb,hpa,cronjobs,ingress
kubectl get --raw /apis/metrics.k8s.io/v1beta1/namespaces/fastapi-platform/pods
```

## Verification and rollback

Verify every API readiness endpoint through its Service and then the public
ingress, including an authenticated WebSocket connection and the payment
callback URL. Run the service-owned smoke workflows against the real public
origin using non-production test data. Record the Git revision, all image
digests, migration Job completion, rollout revisions, ingress controller
version, and smoke evidence in the release record.

On failed rollout, stop new traffic, preserve logs/events, and roll back only
to a previously validated image whose schema compatibility has been confirmed.
If a migration itself introduced an incompatible schema, use the approved
service-owned recovery plan; never issue a blind `alembic downgrade` in a
shared production database.

Use [the API autoscaling runbook](kubernetes-autoscaling.md) for HPA metric,
quota, scheduling, and capacity failures. A target environment must validate
real load and node capacity before increasing the default HPA maximum.

## Egress hardening follow-up

The namespace starts with default-deny ingress, but deliberately does not
enforce guessed egress CIDRs. Before exposing the ingress publicly, add
environment-specific egress policy or an egress gateway that explicitly covers
DNS, managed stateful services, object storage, SMTP/SMS, and the payment
provider. Validate denied-path behavior before enabling it.
