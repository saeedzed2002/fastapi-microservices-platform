# Definition of Done

An executable service is complete only when all applicable evidence exists:

- responsibilities and non-responsibilities are documented;
- API/worker behavior is implemented;
- owned migrations exist and are tested;
- liveness and readiness semantics are correct;
- structured logging is available without sensitive data;
- useful metrics and distributed tracing are available;
- unit tests cover rules and state transitions;
- integration tests cover real adapters and dependencies;
- API and event contract compatibility is validated;
- independent image build succeeds;
- required CI checks pass;
- service README and event/task documentation are current;
- graceful shutdown and redelivery behavior are tested;
- security review findings are resolved or explicitly accepted.

For a non-applicable item, the service README records `N/A` with a reason. Silence is not evidence.

Phase-level completion additionally requires updated architecture/ADRs, validated cross-service workflows, failure-path evidence, and a reviewable commit.
