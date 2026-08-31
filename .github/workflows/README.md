# GitHub Actions

`platform-ci.yml` is the only executable workflow for the current platform
phase. It provides pull-request validation and main-branch conformance proof
in one dependency-ordered graph:

```text
quality
  ├── migration-heads
  ├── image-build + Trivy scan (pull requests only)
  └── integration
        └── kubernetes-conformance (main and manual dispatch only)
```

`image-build` scans every independently deployable pull-request image with
Trivy and fails for fixable `HIGH` or `CRITICAL` vulnerabilities. The
portfolio workflow does not authenticate to a registry or publish images. Its
main-branch `Kind` conformance proof builds local images that are destroyed
with the disposable cluster. A later delivery workflow must scan the exact
image it publishes before registry authentication; it is deliberately outside
the current repository scope.

Action references are immutable commit SHAs and workflow permissions are
read-only. Pull requests receive no repository secrets.

See [CI/CD strategy](../../docs/development/ci-cd.md) for required GitHub
settings, tags, image provenance, and future deployment gates.
