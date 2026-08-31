# Kubernetes resources

This directory is the Phase 9 raw Kubernetes baseline. It remains the
reviewable source model for the Phase 10 Helm charts and is intentionally split
into three independently applied Kustomize entry points:

- `foundation/` creates the namespace, policy, runtime configuration, and
  service account;
- `migrations/` runs every database-owning service's Alembic migration once;
- `workloads/` creates API deployments, workers, scheduled maintenance,
  services, availability budgets, bounded API autoscaling, and the portable
  ingress resource.

Do not apply all directories at once. New environment delivery uses the Helm
charts in `infrastructure/helm/` and follows
`docs/runbooks/kubernetes-deployment.md`. The raw manifests document the same
order and retain zero-digest placeholders for review; they are not a shortcut
around the chart's digest, secret, ingress, and migration gates.

`foundation/runtime-secrets.example.yaml` is documentation only and is
deliberately excluded from every Kustomize resource list. It must never contain
a real credential or be applied unchanged.
