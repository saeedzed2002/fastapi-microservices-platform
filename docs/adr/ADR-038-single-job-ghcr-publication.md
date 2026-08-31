# ADR-038: Single-job GHCR publication

- Status: Accepted
- Date: 2026-09-01
- Owners: platform engineering
- Supersedes: [ADR-037](ADR-037-portfolio-ci-excludes-automatic-registry-publication.md)
- Superseded by: none

## Context

The project keeps `GHCR` publication to demonstrate independently deployable
service-image delivery. The earlier publication design used a GitHub Actions
matrix, so every main-branch revision produced twelve visually similar jobs.
Each job was valid in isolation, but the Actions UI obscured the actual
dependency graph and made one shared scanner failure look like twelve unrelated
failures.

Removing registry publication would remove useful delivery evidence and is not
the requested correction. The job count, rather than the independent-image or
exact-image scan requirement, is the problem to solve.

## Decision

One `publish-ghcr` job runs after quality, migration, integration, and Kind
conformance. It builds every service image from the checked-out revision,
scans every exact local image with the existing `Trivy` `HIGH`/`CRITICAL` gate,
authenticates to `GHCR` only after all scans pass, and then serially tags and
pushes the immutable service images.

The workflow retains independently deployable images, immutable tags, OCI
source/revision/version labels, and a same-artifact scan gate. It removes the
publication matrix only; it does not combine services into one image or create
an automatic Kubernetes deployment.

## Consequences

### Positive

- Main-branch Actions presents one publication job instead of twelve similar
  jobs.
- A shared scanner failure is reported once while preserving the service name
  in the failed scan step.
- Registry authentication occurs only after every image has passed its exact
  local-image scan.

### Negative and risks

- Image build, scan, and publish work is serialized, so the one job can take
  longer than the former parallel matrix.
- A failure for one image blocks registry publication for all images of that
  revision.
- The job is delivery evidence only; no target Kubernetes environment is
  selected or changed.

## Alternatives considered

- Retain the per-service matrix: rejected because it creates unnecessary UI
  and operational noise for this project.
- Remove `GHCR` publication: rejected because it removes requested delivery
  evidence rather than reducing the job count.
- Publish one combined application image: rejected because it violates the
  independent service-image boundary.

## Compatibility and migration

No public API, event schema, database schema, Kubernetes workload topology, or
service ownership changes. The image repository paths and immutable tag scheme
remain unchanged. Existing images remain valid. The workflow change applies to
new main-branch revisions only.

## Validation

- Static CI tests require exactly one non-matrix publication job, every service
  image scan, and registry authentication after every scan step.
- Existing quality, migration, integration, and Kind conformance stages remain
  prerequisites of publication.
- The delivery documentation distinguishes image publication from production
  deployment.

## Related material

- [ADR-027](ADR-027-raw-kubernetes-delivery-baseline.md)
- [ADR-028](ADR-028-kubernetes-conformance-ci.md)
- [ADR-029](ADR-029-helm-packaging-and-controlled-migrations.md)
- [ADR-037](ADR-037-portfolio-ci-excludes-automatic-registry-publication.md)
- [Kubernetes deployment runbook](../runbooks/kubernetes-deployment.md)
- [CI/CD strategy](../development/ci-cd.md)
