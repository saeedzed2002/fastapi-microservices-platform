# End-to-End Tests

Cross-service tests begin when executable services exist.

Planned critical workflows include:

- registration through customer profile creation;
- catalog/media upload and readiness;
- concurrency-safe stock and cart behavior;
- checkout through inventory, payment, confirmation, invoice, and notification;
- authenticated Chat persistence, acknowledgement, fan-out, reconnect, and multi-pod delivery;
- recovery from duplicate events and infrastructure outages.

E2E tests use isolated data, bounded polling of observable state, and deterministic controls where possible. Fixed sleeps are not a synchronization strategy.

`test_phase6_checkout_notification.py` is opt-in because it creates isolated
local product, stock, customer, order, invoice, and SMTP test data. Start the
local platform and run it with `RUN_E2E=1`.

The checkout scenario is implemented once in `checkout_workflow.py`. Compose
uses the edge URL through `E2E_BASE_URL`; the disposable Kubernetes conformance
Job supplies individual `E2E_*_BASE_URL` values for the in-cluster
`customer-service`, `catalog-service`, `inventory-service`, and
`order-service` and `shipping-service` `ClusterIP` services. The test therefore remains the same
business workflow in both environments without pretending that the Kind test
exercises public ingress or TLS.

`test_phase18_shipping.py` reuses that checkout evidence, waits for the
Shipping consumer to create its local shipment, exercises an idempotent
administrator transition through the edge, then waits for the Order Kafka
consumer to update the customer-facing projection.

`test_phase12_resilience.py` is additionally limited to the disposable Compose
topology because it controls Docker Compose service lifecycle. It never runs
inside the Kind E2E Pod or against a remote environment.
