# CI/CD Strategy

CI/CD evolves with real repository capabilities. A check is not simulated before its tool or artifact exists, but becomes mandatory once introduced.

## Current workflow

`Platform CI and Delivery` is the single executable workflow. It runs on every
pull request, every push to `main`, and manual validation. It intentionally has
no path filters because root dependencies, contracts, shared technical
libraries, workflows, and infrastructure affect multiple bounded contexts.

The `quality` job validates architecture artifacts, JSON contracts, raw
Kubernetes rendering with a checksum-verified `kubectl`, Helm lint/render with
a checksum-verified Helm client, the lock, formatting,
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
`kubernetes-conformance`. It downloads checksum-verified `kubectl v1.36.1`,
`Kind v0.32.0`, and `Helm v4.2.4`, builds every service image from the
checked-out revision, and loads those local images into a disposable `Kind`
cluster. The job installs the foundation chart, applies only the test-only
PostgreSQL, Kafka, RabbitMQ, Redis, MinIO, Mailpit, and runtime Secret inputs,
then installs the application chart. It checksum-verifies and loads the
test-only `metrics-server` release so each API HPA receives a real CPU metric.
Helm migration hooks complete before API and worker workloads roll out. The job then executes an in-cluster
`/health/ready` smoke Job followed by the existing checkout to inventory
commit, invoice, and email E2E workflow. The E2E Job runs from the restricted
application namespace through workload `ClusterIP` Services; it therefore
proves application behavior and namespace ingress policy, not public `Ingress`
routing. The job always destroys the cluster and exports diagnostics if the
proof fails. This is deployment evidence for repository charts, not a
production delivery environment: it has no real provider credentials, public
ingress, certificate, external managed-state dependency, multi-node capacity,
or a synthetic HPA scale-out load test.

The repository is a portfolio project, so a validated push to `main` does not
authenticate to `GHCR`, publish images, or request `packages: write`.
`kubernetes-conformance` builds local images from the checked-out revision and
destroys them with the disposable cluster. This is real chart and business-flow
evidence, but it is not registry-release or production-deployment evidence.
Any later release workflow must build, scan with the `HIGH`/`CRITICAL` gate,
attest, and publish the same image artifact only after explicit release scope
and environment controls are approved.

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

## Main-branch validation boundary

```text
validated commit
  -> service migrations and integration workflow
  -> disposable Kind chart installation
  -> readiness, HPA-metrics, smoke, and business E2E proof
  -> destroy local images and disposable cluster
```

The current phase has no registry release. When an environment is introduced,
a separate release workflow must build and attest once, scan that exact image,
and promote the same immutable digest after explicit approval rather than
rebuilding it per environment.

## Migrations and rollback

- Migrations are service-owned and never run independently on every replica startup.
- Delivery uses a controlled Job or migration stage.
- Rolling releases prefer expand-migrate-contract schema changes.
- A failed migration stops rollout and exposes diagnostics.
- Application rollback is performed only when the deployed schema remains compatible.
- Destructive contract/database changes require staged coexistence and an explicit recovery plan.

## Controlled CD

CD is introduced only after Kubernetes deployment exists and its raw resources are stable. It is not an uncontrolled `kubectl apply` command. Environments, approvals, credentials, migration gates, readiness, smoke scope, rollback triggers, and audit history must be defined first.

The current validation boundary ends after successful `Kind` conformance, not
at a registry digest or runtime deployment. Phase 10 supplies Helm migration
hooks and release values; a later promotion workflow must consume a previously
published digest, require explicit environment approval, execute a controlled
chart upgrade, validate rollout/readiness and bounded smoke tests, and permit
rollback only when the schema remains compatible.

## Required GitHub settings

Before relying on delivery, protect `main`: require pull requests, require the
`quality`, `migration-heads`, `image-build`, `integration`, and
`kubernetes-conformance` checks, require up-to-date branches, restrict direct
pushes, and prohibit required-check bypass. Configure Actions with read-only
defaults; this portfolio repository does not require `GITHUB_TOKEN` package
writes. Enable Dependency Graph, Dependabot alerts,
Dependabot security updates, and Dependabot version updates; the committed
configuration checks `uv`, GitHub Actions, Docker Compose, and service
Dockerfiles weekly.
