# Chat support queue runbook

## Purpose

Chat support conversations begin with one `customer` participant and state
`queued`. An agent with an `admin` or `support_agent` role reads queue metadata,
then claims exactly one conversation. After a claim, only the customer and the
assigned agent are Chat participants.

## Customer flow

1. Call `POST /api/v1/chat/support/conversations` with the customer's bearer
   token. A new conversation returns `201`; an existing active request returns
   `200` with the same conversation identifier.
2. Use the returned identifier only in the client application. The customer can
   send through the existing `chat.send_message.v1` WebSocket frame while the
   conversation is queued or claimed.
3. Inspect durable history through the existing messages endpoint after a
   reconnect. Do not treat Redis fan-out as message storage.

## Agent flow

1. Call `GET /api/v1/chat/support/queue`. The response intentionally excludes
   message content.
2. Call `POST /api/v1/chat/support/conversations/{conversation_id}/claim`.
   A `200` response grants Chat membership. A `409` response means another
   agent already claimed or closed the conversation; refresh the queue instead
   of retrying the same claim.
3. Use the normal Chat REST and WebSocket APIs only after a successful claim.
4. Call `POST /api/v1/chat/support/conversations/{conversation_id}/release`
   before transferring unfinished work. The endpoint returns `204` and removes
   the current agent's Chat membership.
5. Call `POST /api/v1/chat/support/conversations/{conversation_id}/close` when
   work is complete. Closing preserves history but blocks new message writes.

## Access failure triage

- `403`: the access token lacks the `customer`, `admin`, or `support_agent`
  role required by the endpoint.
- `404` after another agent claims: expected authorization behavior; the agent
  is no longer a participant and cannot inspect the conversation.
- `409` during claim: expected race protection. Do not retry blindly.
- `409` while sending: the assigned agent closed the conversation. Create a
  new support conversation if the customer needs further help.

## Recovery and audit

Queue and assignment state live in Chat PostgreSQL. Redis loss can delay
realtime delivery but cannot make another agent a participant. If an agent
disconnects or changes shifts, release the conversation deliberately; no
automatic lease expiry is implemented because an automatic reassignment could
silently interrupt an active customer conversation.
