# ADR-017 — Realtime Chat delivery and Media access

- Status: `Accepted`
- Date: `2026-08-26`
- Owners: chat-service, media-service, platform architecture
- Supersedes: none
- Superseded by: none

## Context

Chat requires durable conversations and messages, low-latency delivery across
multiple pods, reconstructible presence, reconnect recovery, and private
attachments. `ADR-007` already restricts Redis to ephemeral state, while the
architecture requires a committed Message before a sender acknowledgement or
realtime publication.

The existing Media API authorizes ordinary asset reads only for the asset owner.
Persisting a Media asset ID in Chat alone would therefore make an attachment
unreadable by other conversation participants. Making chat attachments public,
sharing the sender's bearer token, or letting Media read Chat tables would break
the platform's authorization and ownership boundaries.

## Decision

Chat owns conversations, participant membership, messages, attachment
associations, and participant read cursors in its own PostgreSQL database.
Each sender supplies a UUID `client_message_id`; a unique sender/client key
makes retrying a WebSocket send idempotent. Message history uses the stable
`created_at,id` ordering and an opaque cursor. Clients deduplicate delivery
frames by immutable `message_id` after reconnect.

The client connects to `/api/v1/chat/ws` without a credential in the URL and
must send `chat.authenticate.v1` as its first frame. A valid access token is
required before any other operation. Every message write completes its local
PostgreSQL transaction before `chat.message_ack.v1` is sent. The server then
fans out locally and publishes the committed message notification to the
versioned Redis channel `fastapi-platform:chat:messages:v1`.

Redis publication, subscription, and presence failures are fail-open for the
already committed message: the sender still receives its durable acknowledgement
and the service records the failure. Local connections receive an in-process
fan-out when possible; cross-pod delivery may be delayed until reconnect. A
subscriber reconnects with bounded backoff. Redis Pub/Sub is never used as a
durable queue. Presence is a TTL-backed sorted-set membership per subject; an
unavailable Redis returns `unknown`, never a false `offline` assertion.

Chat validates an attachment before its message transaction by forwarding the
authenticated sender's bearer token to Media's existing owner-authorized asset
read API. The asset must be `ready` and have purpose `chat_attachment`. To
serve a conversation participant later, Chat authorizes membership first, then
calls a Media-internal versioned endpoint with a short-lived HMAC proof over the
subject, conversation, message, asset, and expiry. Media verifies the proof and
its own asset lifecycle before returning a short-lived download URL. The shared
secret is external configuration, must be independently rotatable, and is never
sent to clients or logged. Media continues to own bytes, object keys, and URL
generation; it does not query Chat's database.

`contracts/realtime/chat.v1.schema.json` is the canonical client protocol.
Breaking client-frame changes require a new protocol version. No Chat Kafka
event is introduced in this phase because Redis delivery is deliberately
ephemeral and no independent durable consumer has been identified.

## Consequences

### Positive

- Durable message truth survives Redis loss and pod termination.
- Retries cannot create duplicate messages for the same sender client key.
- Multi-pod delivery avoids process-local connection assumptions.
- Attachment access is private without shared databases, public objects, or
  bearer-token delegation to recipients.
- The protocol makes acknowledgement, deduplication, cursor, and failure
  semantics explicit for clients.

### Negative and risks

- Redis Pub/Sub provides no replay; reconnect history remains mandatory.
- Cross-pod fan-out can be missed after a Redis outage or a commit-to-publish
  crash. A future guaranteed relay requires a separate ADR and durable intent.
- HMAC service credentials introduce rotation and internal-network controls.
- Media unavailability rejects a new attachment-bearing message, while text-only
  messages remain available.
- Presence is approximate and can remain stale until the configured TTL expires.

## Alternatives considered

- Redis as the Message store or acknowledgement boundary: rejected because a
  flush, outage, or Pub/Sub loss would lose durable messages.
- Query-string WebSocket bearer tokens: rejected because URLs are commonly
  retained by logs, browser history, and proxies.
- Public chat attachment URLs or sender-token reuse: rejected because either
  exposes private assets or transfers credentials between principals.
- Media querying Chat data: rejected because it violates service-owned database
  boundaries and creates direct coupling.
- A durable Chat relay immediately: deferred because no external durable Chat
  consumer exists in this phase, and reconnect recovery covers the stated
  realtime delivery requirement.

## Compatibility and migration

This adds the independently versioned `chat.v1` protocol and does not change an
existing REST or Kafka contract. Redis keys and channels are namespaced and
versioned so rolling deployments can overlap. Loss or flush of Redis requires
no PostgreSQL migration. The HMAC proof endpoint is internal and versioned
separately from public Media APIs; secret rotation accepts a configured previous
secret only during an explicitly documented overlap window.

## Validation

- Validate canonical client and server frame examples against the JSON Schema.
- Prove duplicate `client_message_id` submissions return the original durable
  Message and do not create a second row.
- Stop Redis while sending a Message and verify a durable acknowledgement and
  history recovery after reconnect.
- Run two Chat instances against one Redis instance and verify a committed
  Message reaches connections on the other instance exactly once per origin
  publication; clients still deduplicate by `message_id`.
- Verify a non-member cannot send, read history, mark read, retrieve presence,
  or obtain a Media attachment URL.
- Verify an owner, ready, `chat_attachment` asset is required and that a forged,
  expired, or mismatched Media access proof is rejected.

## Related material

- [Architecture overview](../architecture/overview.md)
- [Communication and consistency](../architecture/communication-and-consistency.md)
- [Service boundaries](../architecture/service-boundaries.md)
- [ADR-007 — Restrict Redis to ephemeral platform state](ADR-007-redis-ephemeral-state.md)
- [Realtime Chat diagram](../diagrams/realtime-chat.md)
- [Chat protocol contract](../../contracts/realtime/chat.v1.schema.json)
