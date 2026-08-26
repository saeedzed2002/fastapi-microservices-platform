# Contract Registry

This directory is the canonical, language-neutral source of truth for cross-service contracts.

## Layout

- `events/` contains the standard Kafka envelope and, in later phases, versioned event payload schemas.
- `openapi/` contains shared API schema fragments and exported per-service OpenAPI contracts once services exist.
- `realtime/` contains versioned bidirectional client-frame protocols for persistent realtime APIs.
- `catalog.json` indexes active and reserved contracts, owners, consumers, delivery expectations, and schema locations.
- `catalog.schema.json` defines the machine-readable structure enforced by the Phase 0 validation workflow.

Future code under `libs/contracts` may provide Pydantic models, validators, or generated bindings derived from these files. It must not become a second independently editable contract source.

## Contract lifecycle

Contracts use these states:

- `reserved`: the architecture reserves a name and owner, but the payload/API schema is not designed.
- `proposed`: a complete contract is under review.
- `active`: producers and consumers may rely on the contract.
- `deprecated`: supported during a documented migration window.
- `retired`: no longer produced or supported after compatibility obligations end.

## Compatibility

- Breaking API changes require a new API version.
- Breaking event payload or semantic changes require a new event type version.
- Additive event changes are allowed only when old consumers can safely ignore the new fields.
- Existing required fields cannot be removed, renamed, or assigned an incompatible type.
- A producer does not publish a `reserved` contract.
- Contract changes include documentation, compatibility validation, and affected consumer review.
- An `active` base contract is the canonical repository contract. Runtime model enforcement begins when executable producers/consumers are introduced.

## Data handling

Contracts contain only data required by consumers. Passwords, tokens, raw payment credentials, provider secrets, and unnecessary personal data are forbidden in events, errors, logs, and traces.
