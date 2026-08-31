# GitHub Actions

`platform-ci.yml` is the only executable workflow for the current platform
phase. It provides pull-request validation and main-branch delivery proof
in one dependency-ordered graph:

```text
quality
  ├── migration-heads
  ├── image-build + Trivy scan (pull requests only)
  └── integration
        └── kubernetes-conformance (main and manual dispatch only)
              └── publish-ghcr: build, scan, and publish all services (main only)
```

`image-build` scans every independently deployable pull-request image with
Trivy and fails for fixable `HIGH` or `CRITICAL` vulnerabilities. On `main`,
the single `publish-ghcr` job builds every local image, scans each exact local
tag, then authenticates and publishes only after every scan passes. It keeps
the independent service images and immutable tags without presenting twelve
similar jobs in the Actions UI. `publish-ghcr` is delivery, not deployment.

Action references are immutable commit SHAs. The workflow grants read-only
permissions by default and grants `packages: write` only to the single `GHCR`
publish job. Pull requests never receive package-write permission or repository
secrets.

See [CI/CD strategy](../../docs/development/ci-cd.md) for required GitHub
settings, tags, image provenance, and future deployment gates.
