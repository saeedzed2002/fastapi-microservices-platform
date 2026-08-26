# Chat realtime delivery and attachment access

## Detection

Investigate when `chat_fanout_publish_failed`,
`chat_fanout_subscriber_unavailable`, `chat_presence_unavailable`, or
`websocket_connection_rate_limit_unavailable` appears; when WebSocket
disconnect/error rates rise; or when users report delayed conversations or
attachment failures.

## Impact

`PostgreSQL` remains the Chat source of truth. A Redis Pub/Sub outage can delay
cross-pod delivery and make presence `unknown`, but it cannot delete committed
Messages. Reconnecting clients recover history with the per-conversation
`after` cursor and deduplicate frames by `message_id`.

Redis-backed connection rate limiting is intentionally fail-closed. During a
Redis outage, new WebSocket connections can be refused while existing
connections continue durable message submission. This is an authentication-abuse
control, not a durability failure.

An attachment URL failure can result from Media outage, an unready/deleted
asset, an invalid or expired Chat-to-Media proof, or a configuration secret
mismatch. No client receives the internal proof or secret.

## Immediate checks

1. Check Chat readiness and database connectivity at `/health/ready`.
2. Check Redis health, latency, connections, and the channel
   `fastapi-platform:chat:messages:v1` from within the trusted runtime network.
3. Inspect Chat logs for the exact safe failure category; do not enable payload
   or token logging to debug it.
4. Compare `CHAT_MEDIA_INTERNAL_ACCESS_SECRET` and `MEDIA_CHAT_ACCESS_SECRET`
   through the secret-management metadata, never by printing their values.
5. Confirm the affected user is a current Chat participant and the asset is a
   ready `chat_attachment` through the normal authenticated APIs.

## Safe mitigation and recovery

1. Restore Redis connectivity before scaling Chat pods or changing rate limits.
2. Ask affected clients to reconnect and request history after their last stable
   cursor. Do not replay Redis Pub/Sub messages or synthesize database rows.
3. For a Media secret rotation, configure the previous secret only for the
   documented overlap, deploy Media and Chat consistently, verify proof success,
   then remove the previous secret.
4. If an asset is not ready, retain the durable Message and retry the recipient
   download after Media processing completes. Do not bypass asset lifecycle by
   exposing an object-storage key or a public bucket policy.

## Verification

1. Send a text Message and confirm a sender `chat.message_ack.v1` after it is
   visible in history.
2. With two Chat instances, confirm a recipient on the second instance receives
   `chat.message.v1`; then reconnect and confirm history returns the same
   `message_id`.
3. Verify an unauthorized subject receives neither history nor an attachment
   URL, and that an expired HMAC proof is rejected by Media.

## Escalation and follow-up

Escalate a persistent Redis outage to platform operations and a proof mismatch
to the owners of Chat, Media, and secret management. Record affected interval,
connection rejection rate, subscriber recovery time, missing realtime reports,
and whether durable history recovery succeeded. A requirement for guaranteed
eventual cross-pod fan-out needs a new ADR and a durable relay; do not silently
repurpose Redis Pub/Sub as one.
