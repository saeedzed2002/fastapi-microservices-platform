# Phase 7 Plan — Realtime Chat

## Outcome

Deliver an independently deployable `Chat Service` whose `PostgreSQL` database
is the durable source of truth for conversations, messages, attachments, and
per-participant read state. `Redis` supplies best-effort cross-pod fan-out and
reconstructible presence only.

## Scope

- authenticated versioned `HTTP` conversation, history, unread, and presence APIs;
- an authenticated versioned `WebSocket` client-frame protocol with sender acknowledgements;
- idempotent message submission by sender-scoped client message IDs;
- commit-before-acknowledgement and commit-before-fan-out delivery ordering;
- stable message cursors for reconnect recovery and client frame deduplication;
- explicit `Redis` degradation behavior and bounded subscriber reconnection;
- durable references to ready `Media Service` assets, with an explicit recipient-access
  authorization design before attachment download is exposed;
- service-owned migration, image, Compose workload, observability, documentation, and tests.

## Non-goals

Typing indicators, message editing/deletion, reactions, group administration,
push notifications, message search, legal retention automation, and guaranteed
eventual realtime fan-out after a `Redis` publication failure are deferred.

## Delivery sequence

1. Define the client protocol, cursor semantics, `Redis` failure policy, and attachment access boundary.
2. Add the service-owned data model, migration, REST history/read APIs, and token authentication.
3. Add the `WebSocket` connection manager, durable sender acknowledgement, and local fan-out.
4. Add Redis Pub/Sub and TTL-backed presence, proving that loss of Redis does not lose messages.
5. Integrate authorized Media attachments, Compose, CI, and runtime-facing documentation.

## Dependency selection

`redis-py` `8.1.0`, `FastAPI` `0.141.1`, `HTTPX` `0.28.1`, and the existing
`SQLAlchemy`/`asyncpg` stack are already locked in the workspace. Before
implementation, the Phase 7 review verified the asynchronous `Redis` client and
separate `PubSub` connection model against the official `redis-py`
documentation. The service uses only stable asynchronous Pub/Sub and sorted-set
presence commands, remains compatible with the local `Redis` `8.10.0` baseline,
and records no durable truth in Redis.
