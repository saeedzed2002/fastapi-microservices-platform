# Shared Technical Libraries

`libs/` is reserved for small cross-cutting technical primitives introduced when executable consumers exist.

Allowed examples:

- generated or runtime contract validation;
- request/correlation/trace context propagation;
- structured logging setup;
- generic error-envelope helpers;
- test fixtures and infrastructure helpers;
- generic platform adapters with no business semantics.

Forbidden examples:

- shared `Product`, `Order`, `Payment`, `Inventory`, or `User` models;
- another service's ORM models or repositories;
- shared business rules that erase bounded-context ownership;
- imports that require services to deploy together.

Root `contracts/` remains the canonical editable schema source. Shared libraries are versioned technical implementations and must stay replaceable.
