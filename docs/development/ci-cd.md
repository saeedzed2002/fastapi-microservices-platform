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

A validated push to `main` runs one `publish-ghcr` job after conformance. The
job builds all service images from the checked-out revision, scans every exact
local tag with the `HIGH`/`CRITICAL` Trivy gate, and only then receives
`packages: write` registry authentication. It publishes immutable tags for
each service in one serialized job, rather than creating one Actions job per
service. `kubernetes-conformance` remains real chart and business-flow
evidence; publication is delivery evidence, not a production deployment.

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
  -> build every exact service image
  -> scan every exact local image
  -> one GHCR authentication and serialized immutable pushes
  -> promote immutable digest
  -> controlled service migration step
  -> Kubernetes rollout
  -> readiness and rollout validation
  -> smoke tests
  -> explicit rollback or incident path
```

The current phase publishes each independently deployable image from one
validated job; it does not promote images between environments because
Kubernetes delivery environments do not exist. When those environments are
introduced, the release workflow must build and attest once, then promote the
same digest after explicit approval rather than rebuilding it per environment.

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
not an automatic runtime deployment. Phase 10 supplies Helm migration hooks
and release values; a later promotion workflow must consume a previously
published digest, require explicit environment approval, execute a controlled
chart upgrade, validate rollout/readiness and bounded smoke tests, and permit
rollback only when the schema remains compatible.

## Required GitHub settings

Before relying on delivery, protect `main`: require pull requests, require the
`quality`, `migration-heads`, `image-build`, `integration`, and
`kubernetes-conformance` checks, require up-to-date branches, restrict direct
pushes, and prohibit required-check bypass. Configure Actions with read-only
defaults and grant `GITHUB_TOKEN` package writes only to the publish job.
Enable Dependency Graph, Dependabot alerts, and Dependabot security updates.
Routine Dependabot version updates are deliberately disabled with
`open-pull-requests-limit: 0`: this portfolio repository keeps routine changes
on `main` through explicitly reviewed maintenance commits rather than bot
branches. A real security update may still create a dedicated remediation PR;
that exception is intentional and must be reviewed promptly. The committed
configuration covers `uv`, GitHub Actions, Docker Compose, and service
Dockerfiles.
