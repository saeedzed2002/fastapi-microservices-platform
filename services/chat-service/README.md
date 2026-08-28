# Chat Service

Chat owns conversations, participant membership, messages, durable attachment
references, and participant read cursors. Its PostgreSQL database is the only
durable source of Chat state. It does not access Identity or Media databases.

## Boundaries and dependencies

Chat does not own credentials, Media object bytes, Media asset lifecycle, or
durable presence. It produces no Kafka event and consumes no Kafka event in
this phase; a persisted Chat Message is recovered through its versioned HTTP
history API. It has no Celery task. Its only operational dependencies are its
own PostgreSQL database, Redis for ephemeral fan-out, presence, and rate
limiting, and Media's REST APIs.

## API

- `POST /api/v1/chat/conversations` creates a conversation and always includes
  the authenticated caller as a participant.
- `POST /api/v1/chat/support/conversations` creates or reuses the caller's
  active customer-support request. The customer does not submit an agent ID.
- `GET /api/v1/chat/support/queue` returns metadata-only queued requests to an
  `admin` or `support_agent`.
- `POST /api/v1/chat/support/conversations/{conversation_id}/claim` atomically
  makes one eligible agent the only assigned agent participant. `release`
  returns the request to the queue and removes that agent's membership; `close`
  preserves history and blocks new messages.
- `GET /api/v1/chat/conversations` lists the caller's conversations.
- `GET /api/v1/chat/conversations/{conversation_id}/messages` returns stable
  cursor pages. Use either `before` for older history or `after` for reconnect
  recovery, never both.
- `POST /api/v1/chat/conversations/{conversation_id}/read` advances only the
  caller's durable read cursor.
- `GET /api/v1/chat/presence/{subject_id}` returns `online`, `offline`, or
  `unknown`; `unknown` means Redis cannot make a trustworthy assertion.
- `GET /api/v1/chat/conversations/{conversation_id}/messages/{message_id}/attachments/{asset_id}/download-url`
  creates a recipient-authorized, short-lived Media URL.

## WebSocket

The endpoint is `/api/v1/chat/ws`. Clients must send `chat.authenticate.v1` as
the first frame, then `chat.send_message.v1` or `chat.heartbeat.v1`. A send
uses a caller-scoped `client_message_id`; retries return the original committed
Message with `duplicate: true`. `chat.message_ack.v1` arrives only after the
Chat database commit. Delivery frames can be repeated after reconnect or
cross-pod fan-out, so clients deduplicate by `message_id` and recover gaps from
the history endpoint.

The canonical frame contract is
[`chat.v1.schema.json`](../../contracts/realtime/chat.v1.schema.json).
The support queue REST contract is
[`chat-support.v1.openapi.json`](../../contracts/openapi/chat-support.v1.openapi.json).

## Delivery and attachment boundaries

The service broadcasts locally after a commit and then publishes a notification
to Redis for other pods. Redis failure never rolls back a committed Message.
Redis-backed connection limiting is fail-closed because it protects an exposed
authentication surface; Pub/Sub and presence failure are not authoritative.

Before a message transaction, Chat calls Media with the sender's token and
requires an owner-authorized ready `chat_attachment` asset. For a recipient
download, Chat validates conversation membership and asks Media's internal API
for a URL using a short-lived HMAC proof. The shared secret is external
configuration and must be rotated without exposing it to clients.

## Tests and operations

Run Chat's focused checks with `uv run --package chat-service pytest
services/chat-service/tests -q`; run the opt-in platform flow with `RUN_E2E=1
uv run pytest tests/e2e/test_phase7_realtime_chat.py -q`. Migration and
operational recovery guidance is in
[`chat-realtime.md`](../../docs/runbooks/chat-realtime.md).
