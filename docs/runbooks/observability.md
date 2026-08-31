# Observability collection and alert response

## Detection

Grafana dashboards show HTTP request rate, latency, error ratio, Kafka DLQ
activity, and Chat realtime counters. Prometheus evaluates the alert rules
under `infrastructure/observability/prometheus/rules/`.

## Impact

Telemetry loss reduces diagnosis quality but must not stop customer traffic or
durable processing. Application JSON stdout remains the immediate fallback.
A genuine service outage is separate from Collector or backend unavailability.

## Immediate checks

1. Confirm whether the application health endpoint or only the telemetry
   backend is unavailable.
2. Inspect the Collector health endpoint and internal metrics before changing
   application settings.
3. Query the application `/metrics` endpoint directly from its allowed network
   path and check the `up` target in Prometheus.
4. For a missing trace, check the correlation ID in JSON stdout and determine
   whether export was disabled, sampled, or rejected downstream.
5. For a rising DLQ alert, follow the existing [Kafka DLQ runbook](kafka-dlq.md)
   before replaying anything.

## Safe mitigation

- Disable only `PLATFORM_OBSERVABILITY_ENABLED` when an exporter incident
  materially harms the application process. Do not alter business retry,
  outbox, Kafka, or Celery settings as a telemetry workaround.
- Restart the Collector or local profile only after preserving its diagnostics.
- Do not add request IDs, raw paths, payloads, tokens, or exception text as
  metric labels to investigate an incident.

## Recovery and verification

1. Restore the Collector/backend and wait for its health endpoint.
2. Issue a bounded synthetic request with a fresh correlation ID and retain
   the returned W3C trace identifier.
3. Verify the Prometheus HTTP metric, the JSON log containing that trace
   identifier, and the trace appear in their expected backend.
4. Confirm alert state returns to normal after its configured `for` period.
5. Record dropped telemetry, affected time range, root cause, and whether a
   policy or resource adjustment is needed.

## Escalation and follow-up

Platform engineering owns all initial alerts. Escalate suspected customer or
durable-work impact to the owning service operator. Before any target
deployment, define SLOs from measured traffic, alert routing, retention,
access policy, backup/recovery, and capacity ownership; the local thresholds
are deliberately provisional.
