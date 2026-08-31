# GitHub Actions

`platform-ci.yml` is the only executable workflow for the current platform
phase. It provides pull-request validation and main-branch image delivery in
one dependency-ordered graph:

```text
quality
  ├── migration-heads
  ├── image-build + Trivy scan (pull requests only)
  └── integration
        └── kubernetes-conformance (main only)
              └── publish-ghcr: build + Trivy scan + publish per service (main only)
```

`image-build` scans every independently deployable pull-request image with
Trivy and fails for fixable `HIGH` or `CRITICAL` vulnerabilities. On `main`,
each `publish-ghcr` matrix entry builds one local image, scans that exact local
tag with the same gate, and only then authenticates and pushes it. A failed or
skipped scan therefore cannot publish an image. `publish-ghcr` is delivery,
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
