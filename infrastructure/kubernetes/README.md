# Kubernetes resources

This directory is the Phase 9 raw Kubernetes baseline. It is intentionally
split into three independently applied Kustomize entry points:

- `foundation/` creates the namespace, policy, runtime configuration, and
  service account;
- `migrations/` runs every database-owning service's Alembic migration once;
- `workloads/` creates API deployments, workers, scheduled maintenance,
  services, availability budgets, and the portable ingress resource.

Do not apply all directories at once. Follow
`docs/runbooks/kubernetes-deployment.md` in order. In particular, replace the
zero digest image placeholders, create `platform-runtime-secrets` and
`ghcr-pull` outside Git, choose a real ingress class/host/TLS secret, and wait
for migration Jobs before workloads.

`foundation/runtime-secrets.example.yaml` is documentation only and is
deliberately excluded from every Kustomize resource list. It must never contain
a real credential or be applied unchanged.
