# Kubernetes conformance overlay

This directory proves the Phase 9 application deployment sequence in a
disposable `Kind` cluster. It is not a production overlay and must never be
promoted to an environment.

`scripts/run_kubernetes_conformance.sh` does the following:

1. builds every service image and the source-built MinIO image from the current
   checkout as single-platform images without BuildKit provenance attestations,
   because `Kind` imports those test-only images into the node's containerd
   content store;
2. creates a `Kind v0.32.0` cluster using the exact pinned Kubernetes
   `v1.36.1` node image;
3. pulls each disposable dependency by its pinned digest, retags it with a
   deterministic local conformance tag, then loads those and the test-only
   images into the node without permitting runtime image pulls;
4. applies `foundation`, waits for PostgreSQL, Kafka, RabbitMQ, Redis, MinIO,
   and Mailpit, applies migrations, then workloads;
5. runs `platform-health-smoke` from the restricted application namespace;
6. exports diagnostics on failure and deletes the cluster in all cases.

The default always builds images from the checked-out source. Local diagnosis
may set `CONFORMANCE_SKIP_IMAGE_BUILD=true` only after every listed
`fastapi-platform/*:conformance` image has already been built from that same
checkout. CI never sets this escape hatch.

The `fastapi-platform` namespace remains subject to the production-equivalent
restricted Pod Security Standard. Stateful test dependencies live in the
separate `fastapi-platform-dependencies` namespace because their upstream
images are not part of the application workload security boundary.

The secret values in `foundation/runtime-secrets.yaml` are deterministic,
non-production test data. The overlay has no real payment or SMS credentials,
no public ingress hostname, and no trusted TLS configuration. Production uses
the digest-only base manifests and the operator process in
`docs/runbooks/kubernetes-deployment.md`.
