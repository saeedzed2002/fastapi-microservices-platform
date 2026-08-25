# CI/CD Strategy

CI/CD evolves with real repository capabilities. A check is not simulated before its tool or artifact exists, but becomes mandatory once introduced.

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
  -> build affected service image once
  -> tag with service version and Git SHA
  -> push to GHCR
  -> promote immutable digest
  -> controlled service migration step
  -> Kubernetes rollout
  -> readiness and rollout validation
  -> smoke tests
  -> explicit rollback or incident path
```

Images are not rebuilt separately for each environment. Environment promotion uses the same verified digest.

## Migrations and rollback

- Migrations are service-owned and never run independently on every replica startup.
- Delivery uses a controlled Job or migration stage.
- Rolling releases prefer expand-migrate-contract schema changes.
- A failed migration stops rollout and exposes diagnostics.
- Application rollback is performed only when the deployed schema remains compatible.
- Destructive contract/database changes require staged coexistence and an explicit recovery plan.

## Controlled CD

CD is introduced only after Kubernetes deployment exists and its raw resources are stable. It is not an uncontrolled `kubectl apply` command. Environments, approvals, credentials, migration gates, readiness, smoke scope, rollback triggers, and audit history must be defined first.
