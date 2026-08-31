# ADR-037: Portfolio CI excludes automatic registry publication

- Status: Superseded
- Date: 2026-08-31
- Owners: platform engineering
- Supersedes: none
- Superseded by: [ADR-038](ADR-038-single-job-ghcr-publication.md)

## Context

The repository is a public portfolio project, not a deployed environment. The
previous main-branch workflow rebuilt, scanned, and published one image for
each independently deployable service. That correctly protected an operational
registry release, but created twelve similar `GHCR` jobs on every main push,
requested package-write permission, and presented registry delivery as current
evidence when no environment consumes those images.

The disposable Kind conformance job already builds all service images from the
checked-out revision, installs the Helm charts, and executes the in-cluster
business workflow. It is the relevant executable evidence for this portfolio.

## Decision

The executable workflow ends at quality, migration, integration, and disposable
Kind conformance. It does not authenticate to `GHCR`, request package-write
permission, push an OCI image, or create a per-service main-branch publication
matrix.

Pull-request image builds retain their `Trivy` `HIGH`/`CRITICAL` gate. The
Kind job builds local test images only and destroys them with the disposable
cluster. If actual registry delivery becomes a project goal, a separately
approved release workflow must build, scan, attest, and publish the same
immutable image artifact before an operator promotes it.

## Consequences

### Positive

- Main-branch CI presents the architecture and in-cluster business proof
  without twelve redundant registry-release jobs.
- The workflow has no registry credentials or package-write permission.
- The repository makes no false claim that it currently publishes deployable
  image releases.

### Negative and risks

- The repository no longer produces `GHCR` image-digest release evidence.
- An environment operator must supply independently built, scanned, immutable
  image digests before using the deployment runbook.
- A future release workflow must restore an exact-artifact scan gate rather
  than treating a pull-request scan as delivery evidence.

## Alternatives considered

- Keep the automatic per-service `GHCR` matrix: rejected because it is
  operational delivery scope that the portfolio does not use.
- Publish all service images from one serial job: rejected because it hides the
  same unused registry-release work rather than removing it.
- Publish one combined application image: rejected because it violates the
  independently deployable service-image boundary.

## Compatibility and migration

No public API, event schema, database schema, Kubernetes workload topology, or
service ownership changes. Existing registry packages are not selected by the
current workflow. The immutable-digest requirement in Helm delivery values
remains; this decision changes only how a future release artifact is produced.

## Validation

- Static CI tests require the workflow to omit registry authentication, image
  push commands, package-write permission, and the publication matrix.
- Pull-request image scans and main-branch Kind conformance remain explicit
  workflow stages.
- The deployment runbook and CI documentation state that conformance is not
  registry-release or production-deployment evidence.

## Related material

- [ADR-027](ADR-027-raw-kubernetes-delivery-baseline.md)
- [ADR-028](ADR-028-kubernetes-conformance-ci.md)
- [ADR-029](ADR-029-helm-packaging-and-controlled-migrations.md)
- [Kubernetes deployment runbook](../runbooks/kubernetes-deployment.md)
- [CI/CD strategy](../development/ci-cd.md)
