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
