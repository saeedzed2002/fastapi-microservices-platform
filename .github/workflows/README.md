# GitHub Actions

`platform-ci.yml` is the only executable workflow for the current platform
phase. It provides pull-request validation and main-branch image delivery in
one dependency-ordered graph:

```text
quality
  ├── migration-heads
  ├── image-build + Trivy scan (pull requests only)
  └── integration
        └── publish-ghcr (main only)
```

`image-build` scans every independently deployable image with Trivy and fails
for fixable `HIGH` or `CRITICAL` vulnerabilities. `publish-ghcr` is delivery,
not deployment. It publishes immutable OCI images
only after validation; no workflow deploys to Kubernetes before reviewed
Kubernetes and Helm resources, environment gates, migration Jobs, readiness
checks, smoke tests, and rollback behavior exist.

Action references are immutable commit SHAs. The workflow grants read-only
permissions by default and grants `packages: write` only to the `GHCR` publish
job. Pull requests never receive package write permission or repository
secrets.

See [CI/CD strategy](../../docs/development/ci-cd.md) for required GitHub
settings, tags, image provenance, and future deployment gates.
