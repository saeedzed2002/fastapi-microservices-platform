# Workflow Roadmap

Phase 0 contains one project-dependency-free structural workflow. It parses JSON, checks local Markdown links and code fences, validates the contract catalogue and canonical examples against their JSON Schemas, applies additional cross-field invariants, and rejects trailing whitespace. The only external action is the officially verified `actions/checkout` release pinned to its full immutable commit SHA; the job uses explicit read-only permissions and disables persisted credentials.

Phase 1 extends CI after the runtime toolchain is officially verified. It will validate the lockfile, formatting, lint, typing, unit tests, contracts, integration behavior, image builds, and security scans as those capabilities exist.

Later delivery builds each affected image once, tags and promotes an immutable digest, runs controlled migrations, verifies rollout/readiness, executes smoke tests, and handles rollback explicitly. Uncontrolled deployment commands are not the CD strategy.
