# CI/CD Strategy

CI/CD evolves with real repository capabilities. A check is not simulated before its tool or artifact exists, but becomes mandatory once introduced.

## Current workflow

`Platform CI and Delivery` is the single executable workflow. It runs on every
pull request, every push to `main`, and manual validation. It intentionally has
no path filters because root dependencies, contracts, shared technical
libraries, workflows, and infrastructure affect multiple bounded contexts.

The `quality` job validates architecture artifacts, JSON contracts, raw
Kubernetes rendering with a checksum-verified `kubectl`, the lock, formatting,
linting, typing, unit tests, the Compose model, and locked Python dependency
vulnerabilities. Editable workspace packages are not published
third-party distributions, so `pip-audit` excludes them and audits their locked
external dependencies. The `migration-heads` job requires one Alembic
head per executable service. Pull requests build each service image
independently and scan it with Trivy for fixable `HIGH` and `CRITICAL`
vulnerabilities. The `integration` job starts only PostgreSQL and the shared
brokers first, runs every service-owned migration, then starts APIs and workers
against the migrated schemas before executing checkout-to-invoice-to-email E2E
and collecting logs on failure. Application processes must never begin
background database work against an unmigrated schema.

Pushes to `main` and manual workflow dispatches additionally run
`kubernetes-conformance`. It downloads checksum-verified `kubectl v1.36.1`
and `Kind v0.32.0`, builds every service image from the checked-out revision,
and loads those local images into a disposable `Kind` cluster. The job applies
the test-only foundation (including isolated PostgreSQL, Kafka, RabbitMQ,
Redis, MinIO, and Mailpit), waits for dependency readiness, runs controlled
migration Jobs, waits for all API and worker Deployments, and executes an
in-cluster `/health/ready` smoke Job followed by the existing checkout to
inventory commit, invoice, and email E2E workflow. The E2E Job runs from the
restricted application namespace through the workload `ClusterIP` services;
it therefore proves application behavior and the namespace ingress policy, not
public `Ingress` routing. The job always destroys the cluster and exports
diagnostics if the proof fails. This is deployment evidence for the repository
manifests, not a production delivery environment: it has no real provider
credentials, public ingress, certificate, or external managed-state dependency.

Only a validated push to `main` can run `publish-ghcr`. That job receives
`packages: write` and no broader write permission, authenticates with the
workflow-scoped `GITHUB_TOKEN`, and publishes one image per service to
`ghcr.io/saeedzed2002/fastapi-microservices-platform/<service>`. Images receive
`sha-<full-git-sha>` and `<service-version>-<short-git-sha>` tags plus OCI
source, revision, and version labels. No `latest` tag is published and the
workflow summary records the resulting digest.

`pip-audit 2.10.1` and `Trivy Action 0.36.0` were selected from their official
releases on `2026-08-25`; the former supports Python `3.14` and is locked as a
development dependency, while the latter is immutably pinned in the workflow.
The workflow uses only immutable references to `actions/checkout`,
`astral-sh/setup-uv`, and `aquasecurity/trivy-action`, the hosted-runner Docker
CLI, and GitHub's built-in registry token.

## Pull Request CI target

- formatting validation;
- linting;
- type checking;
- unit tests;
- integration tests with real dependencies;
- OpenAPI and event contract compatibility tests;
- independent affected-service image builds;
- dependency and container scans;
- repository, documentation, migration, and generated-artifact checks.

All actions are officially verified and immutably pinned. Workflow permissions are explicit and minimal. Untrusted pull-request code does not receive repository secrets.

Initially all applicable checks run. Later affected-service detection may optimize CI, but changes to root dependency metadata, locks, shared libraries, contracts, infrastructure, or workflows trigger all relevant consumers. A required workflow is not silently skipped by fragile path filters.

## Main-branch delivery target

```text
validated commit
  -> build and publish the exact validated source revision
  -> tag with service version and Git SHA
  -> push to GHCR
  -> promote immutable digest
  -> controlled service migration step
  -> Kubernetes rollout
  -> readiness and rollout validation
  -> smoke tests
  -> explicit rollback or incident path
```

The current phase rebuilds the exact validated Git revision in the publish job;
it does not yet promote images between environments because Kubernetes delivery
environments do not exist. When those environments are introduced, the release
workflow must build and attest once, then promote the same digest after explicit
approval rather than rebuilding it per environment.

## Migrations and rollback

- Migrations are service-owned and never run independently on every replica startup.
- Delivery uses a controlled Job or migration stage.
- Rolling releases prefer expand-migrate-contract schema changes.
- A failed migration stops rollout and exposes diagnostics.
- Application rollback is performed only when the deployed schema remains compatible.
- Destructive contract/database changes require staged coexistence and an explicit recovery plan.

## Controlled CD

CD is introduced only after Kubernetes deployment exists and its raw resources are stable. It is not an uncontrolled `kubectl apply` command. Environments, approvals, credentials, migration gates, readiness, smoke scope, rollback triggers, and audit history must be defined first.

The current delivery boundary remains the verified immutable `GHCR` digest,
not an automatic runtime deployment. Phase 9 supplies the raw Kubernetes
resources and migration gates; a later promotion workflow must consume a
previously published digest, require explicit environment approval, execute a
controlled service-owned migration Job, validate rollout/readiness and bounded
smoke tests, and permit rollback only when the schema remains compatible.

## Required GitHub settings

Before relying on delivery, protect `main`: require pull requests, require the
`quality`, `migration-heads`, `image-build`, `integration`, and
`kubernetes-conformance` checks, require
up-to-date branches, restrict direct pushes, and prohibit required-check
bypass. Configure Actions with read-only defaults and permit `GITHUB_TOKEN`
package writes for this repository. Enable Dependency Graph, Dependabot alerts,
Dependabot security updates, and Dependabot version updates; the committed
configuration checks `uv`, GitHub Actions, Docker Compose, and service
Dockerfiles weekly.
