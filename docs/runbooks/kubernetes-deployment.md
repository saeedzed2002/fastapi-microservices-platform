# Kubernetes deployment

## Scope and safety boundary

This runbook deploys the Phase 9 raw resources. It does not create a cluster,
an ingress controller, TLS issuer, secret manager, or managed stateful service.
Do not treat a successful `kubectl apply` as proof that migrations, image pulls,
external dependencies, or public routing work.

Use a Kubernetes `v1.37` control plane and a supported `kubectl` client. The
resource layout is:

1. `infrastructure/kubernetes/foundation`
2. `infrastructure/kubernetes/migrations`
3. `infrastructure/kubernetes/workloads`

Never apply all three directories together and never allow API replicas to run
their own migrations.

## Required environment inputs

Before any apply, an environment owner must provide:

- a reviewed Kubernetes ingress controller and its actual `IngressClass`;
- the actual public hostname and a TLS secret named `platform-public-tls`;
- DNS, TLS, and trusted-proxy policy compatible with HTTP and WebSockets;
- reachable external PostgreSQL databases, Kafka, RabbitMQ, Redis, object
  storage, SMTP/SMS configuration where enabled, and the payment-provider
  callback public URL;
- a secret manager or equivalent audited secret-delivery method;
- private-registry pull credentials if `GHCR` packages are not public;
- an explicit egress-policy design for those real dependency endpoints.

The raw ingress has deliberate placeholders. Before deployment, create a
private release overlay that changes its ingress class, host, TLS host, and
`PAYMENT_ZARINPAL_CALLBACK_URL`. Do not commit environment hostnames or
credentials to the shared base resources.

## Release images

The base manifests contain zero digest placeholders and are intentionally not
runnable unchanged. Obtain the exact digests from the validated `publish-ghcr`
workflow for one Git revision. In a private release overlay, replace every
service image with its published immutable digest. The same digest must be
used by its API, worker, and migration Job.

Verify that no placeholder remains before applying:

```bash
kubectl kustomize /secure/release-overlay | grep '0000000000000000000000000000000000000000000000000000000000000000' && exit 1
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

Render locally first:

```bash
kubectl kustomize /secure/release-overlay/foundation >/dev/null
kubectl kustomize /secure/release-overlay/migrations >/dev/null
kubectl kustomize /secure/release-overlay/workloads >/dev/null
```

Apply the foundation and verify its policy objects:

```bash
kubectl apply -k /secure/release-overlay/foundation
kubectl get namespace fastapi-platform
kubectl -n fastapi-platform get configmap platform-runtime-config
kubectl -n fastapi-platform get networkpolicy
```

Migration Jobs have fixed names to make them renderable and auditable. Delete
only prior completed/failed migration Jobs for this platform before creating
the new release's Jobs; do not delete unrelated Jobs:

```bash
kubectl -n fastapi-platform delete job -l platform.fastapi.io/workload=migration --ignore-not-found
kubectl apply -k /secure/release-overlay/migrations
kubectl -n fastapi-platform wait --for=condition=complete job -l platform.fastapi.io/workload=migration --timeout=10m
kubectl -n fastapi-platform get jobs -l platform.fastapi.io/workload=migration
```

If any migration fails, stop. Inspect only the failed Job logs, correct the
release or operational dependency, and rerun from the controlled deletion
step. Do not start or scale workloads to bypass migration failure:

```bash
kubectl -n fastapi-platform get jobs -l platform.fastapi.io/workload=migration
kubectl -n fastapi-platform logs job/<failed-migration-job>
```

Only after all migrations complete, apply workloads and wait for rollout:

```bash
kubectl apply -k /secure/release-overlay/workloads
kubectl -n fastapi-platform rollout status deployment --timeout=10m
kubectl -n fastapi-platform get pods,services,pdb,cronjobs,ingress
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

## Egress hardening follow-up

The namespace starts with default-deny ingress, but deliberately does not
enforce guessed egress CIDRs. Before exposing the ingress publicly, add
environment-specific egress policy or an egress gateway that explicitly covers
DNS, managed stateful services, object storage, SMTP/SMS, and the payment
provider. Validate denied-path behavior before enabling it.
