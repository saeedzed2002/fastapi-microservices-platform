# ADR-019 — Chat support queue assignment

- Status: Accepted
- Date: 2026-08-28
- Owners: chat-service, platform architecture
- Supersedes: none
- Superseded by: none

## Context

The initial Chat foundation permits a caller to create a generic conversation
with explicit participant identifiers. A storefront support experience has a
different authorization model: a customer must start a support request without
selecting an administrator, eligible agents must see only queue metadata before
claiming it, and exactly one agent must become the participant responsible for
the conversation. A second agent must not be able to read messages or continue
to list the conversation after the first claim succeeds.

Chat already owns conversations, membership, messages, and their authorization.
Identity owns accounts and signs the role claims that Chat validates; Chat must
not query Identity tables to find or assign agents.

## Decision

Chat adds a service-owned `support_conversations` record for each support
workflow. Its state is `queued`, `claimed`, or `closed`. A partial unique index
allows at most one active (`queued` or `claimed`) support conversation per
customer. A closed conversation remains readable by its existing participants,
but a new support request creates a new active conversation.

A caller with the `customer` role creates or reuses an active support
conversation through `POST /api/v1/chat/support/conversations`. The customer is
the only initial Chat participant. Agents with either the `admin` or
`support_agent` role can list `GET /api/v1/chat/support/queue`; that API returns
only identifiers and timestamps, never message content.

An agent claims a queue item through `POST
/api/v1/chat/support/conversations/{conversation_id}/claim`. Chat locks the
support row, confirms that it is still queued, changes it to claimed, and adds
the agent's participant record in one PostgreSQL transaction. The row lock
makes simultaneous claims deterministic: one agent succeeds and all others
receive a conflict. Once claimed, normal Chat membership checks give access
only to the customer and assigned agent. The agent can release the conversation
back to the queue or close it; release removes that agent's participant record
in the same transaction.

The existing `chat.v1` WebSocket protocol is unchanged. It continues to
authorize each message by durable Chat membership, commit before acknowledgement,
and publish only after commit. No Chat Kafka event or Celery task is introduced
because no independent durable consumer needs the assignment fact.

## Consequences

### Positive

- Customers cannot select arbitrary administrator identifiers for support.
- Queue readers cannot inspect private message history before a claim.
- Concurrent agents cannot both own the same support conversation.
- Releasing an assignment removes the previous agent's authorization before
  another agent can claim it.
- The workflow stays entirely inside the Chat bounded context and trusts only
  signed Identity role claims.

### Negative and risks

- The initial Identity API has no administrator-role provisioning endpoint;
  production agents need an approved Identity administration workflow that
  issues `admin` or `support_agent` claims.
- The queue exposes the customer subject identifier to eligible agents. It does
  not expose message content, email, phone number, order data, or other profile
  fields.
- A generic conversation endpoint remains separate from this support workflow
  for backwards compatibility. Storefront clients must use the support endpoints
  and must not expose generic participant selection.

## Alternatives considered

- Add every administrator as a participant when the customer creates a
  conversation: rejected because it exposes private history and produces
  multiple simultaneous responders.
- Store assignment only in Redis: rejected because Redis is ephemeral and a
  restart could grant conflicting access to durable messages.
- Have Chat query Identity's database for available administrators: rejected
  because it violates service database ownership.
- Use a distributed lock without a database transaction: rejected because it
  would not atomically change durable assignment and participant membership.

## Compatibility and migration

This is an additive `v1` support API and an additive field on Chat conversation
responses. Existing generic conversations have no `support` metadata and retain
their current behavior. The standalone canonical contract is
`contracts/openapi/chat-support.v1.openapi.json`; the established `chat.v1`
WebSocket frames are unchanged. The migration adds a new table only and does
not rewrite existing conversations or messages.

## Validation

- Apply the Chat migration to PostgreSQL.
- Verify a customer receives one queued conversation even after repeated create
  requests.
- Verify a non-agent cannot list or claim the queue.
- Verify two eligible agents cannot both claim the same conversation.
- Verify a non-claiming agent cannot read history, send a message, or obtain an
  attachment URL after the claim.
- Verify release removes the former agent's access, and closing blocks later
  message writes while preserving history for the customer and assigned agent.

## Related material

- [Chat service README](../../services/chat-service/README.md)
- [Chat support queue runbook](../runbooks/chat-support-queue.md)
- [Chat support API contract](../../contracts/openapi/chat-support.v1.openapi.json)
- [Realtime Chat delivery and Media access](ADR-017-realtime-chat-delivery-and-media-access.md)
- [Service boundaries](../architecture/service-boundaries.md)
