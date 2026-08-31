# Resilience disruption and recovery

## Purpose

Use the Phase 12 E2E suite only against the disposable local Compose topology
or its isolated CI equivalent. It deliberately stops one approved dependency
at a time and proves a durable recovery invariant. It is not authorized for a
shared, staging, or production environment.

## Preconditions

1. Start the local platform after applying service migrations.
2. Confirm all required services are healthy.
3. Set `RUN_E2E=1` and use the repository Compose file.
4. Do not run other checkout, catalog, Cart, or broker-maintenance workflows
   concurrently.

## Execute

```powershell
$env:RUN_E2E = "1"
python -m pytest tests/e2e/test_phase12_resilience.py -q
```

The harness stops only `kafka`, `rabbitmq`, or `redis`, then starts the same
service in a `finally` block. It does not remove containers or volumes.

## Failure interpretation

1. If a service did not restart, inspect its health and container logs before
   repeating the test. Do not delete its volume as a first response.
2. If Kafka recovery fails, inspect the producing service outbox row, its
   publisher log, the consumer group offset, and the Search projection before
   replaying an event.
3. If RabbitMQ recovery fails, inspect the Order `task_intents` row, its
   dispatch attempt/error, the `order.invoice` queue, and the Invoice status.
   A manual task replay must retain the original invoice identifier and remain
   idempotent.
4. If Redis fallback fails, inspect Cart database state and cache error logs.
   Redis must not be treated as the Cart source of truth.
5. Preserve diagnostic timestamps, correlation IDs, and relevant logs before
   changing retry, timeout, broker, or database settings.

## Recovery completion

The test must leave every stopped service running. Verify the normal E2E
workflow after recovery before declaring the local topology usable again. A
successful local test does not establish a target-environment recovery SLO.
