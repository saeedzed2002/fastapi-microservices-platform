# This disposable runner derives from the checked-out order-service image. It
# reuses the locked HTTP, S3, and JWT dependencies used by checkout itself and
# introduces no test-only runtime dependency.
FROM fastapi-platform/order-service:conformance

COPY tests/e2e/checkout_workflow.py /app/checkout_workflow.py
COPY tests/e2e/shipping_workflow.py /app/shipping_workflow.py

CMD ["python", "/app/checkout_workflow.py"]
