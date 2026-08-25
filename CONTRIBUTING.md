# Contributing

## Workflow

Work proceeds incrementally:

```text
specification
  -> architecture review
  -> approved phase plan
  -> implementation
  -> tests
  -> documentation
  -> validation
  -> commit
  -> review
```

Before changing a bounded context, read its service README, relevant contracts, and accepted ADRs.

## Branches and commits

Use a short-lived branch when collaborative review requires it:

- `feature/*`
- `fix/*`
- `chore/*`

Use meaningful conventional commit subjects, for example:

- `feat(order): add transactional outbox`
- `fix(inventory): prevent duplicate reservation`
- `chore(ci): add integration test workflow`
- `docs(adr): document kafka event strategy`

Do not mix unrelated service, infrastructure, and documentation work in one commit.

## Architecture changes

Create or amend an ADR before changing:

- service or data ownership;
- synchronous or asynchronous transport roles;
- durable-delivery or consistency guarantees;
- public API or event compatibility policy;
- authentication or service trust architecture;
- deployment topology;
- a significant platform technology.

## Definition of done

An executable service is not complete merely because endpoints work. Its applicable migrations, health checks, structured logs, metrics, traces, unit/integration/contract tests, image build, CI checks, documentation, graceful shutdown behavior, and security review must also be complete.
