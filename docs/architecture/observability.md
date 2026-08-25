# Observability

Observability is part of service behavior from the first executable implementation. Phase 11 completes platform-wide collection, dashboards, alerts, and tuning; it does not introduce instrumentation for the first time.

## Stack responsibilities

- OpenTelemetry instruments code and propagates context.
- Prometheus stores and queries metrics.
- Grafana visualizes metrics, logs, and traces and hosts operational dashboards.
- Loki centralizes structured logs.
- Tempo stores distributed traces.

The OpenTelemetry Collector topology, sampling, retention, and exporter-failure policy are selected when the implementation stack is officially verified.

## Signal semantics

- Logs describe discrete events and diagnostic context.
- Metrics aggregate numerical behavior over time for trends, SLOs, and alerts.
- Traces connect causally related operations across processes and transports.

## Context identifiers

- `request_id`: one inbound HTTP request.
- `correlation_id`: one logical business workflow across HTTP, Kafka, and Celery.
- `causation_id`: the immediate request/event/task that caused another message.
- `trace_id`: one distributed trace.
- `span_id`: one operation within that trace.

HTTP headers and message/task headers carry standard trace context. Event envelopes preserve correlation and causation explicitly. Delayed or batched consumers may use span links rather than forcing an inaccurate synchronous parent-child relationship.

## Structured logs

Logs use JSON and include applicable fields such as timestamp, level, service, service version, environment, request/correlation/trace/span IDs, event type, and safe message context.

Credentials and sensitive payloads are forbidden. User, order, payment, and event IDs may appear only when required and subject to data-classification, retention, and access policy.

## Metrics

Minimum operational coverage includes:

- HTTP request count, latency, and errors;
- database pool usage and query latency;
- Kafka production, consumption, processing error, and consumer lag;
- outbox backlog count/age and publication failures;
- RabbitMQ queue depth and unacknowledged messages;
- Celery count, duration, retry, and failure;
- Redis latency and error rate;
- WebSocket connections, messages, disconnects, and errors;
- checkout duration, reservation failure, payment failure, and stuck Saga count;
- DLQ volume and replay outcomes.

High-cardinality IDs, raw URLs containing IDs, exception text, and payload values are not metric labels.

## Tracing workflows

Checkout tracing follows the initial HTTP request, local database/outbox operation, Kafka publish and consume spans, Inventory and Payment processing, resulting events, and downstream Celery work where the trace remains meaningful.

Chat traces cover authentication, membership validation, database commit, sender acknowledgement, Redis publication, and local fan-out without recording message content.

## Operability

Dashboards require owned alerts and runbooks. Before production-style deployment, define SLOs, sampling, retention, cardinality budgets, alert thresholds, escalation, and telemetry-backend failure behavior.
