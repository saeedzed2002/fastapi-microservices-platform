from shipping_service.main import app


def test_shipping_openapi_exposes_the_authorized_shipment_command() -> None:
    paths = app.openapi()["paths"]
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/api/v1/shipping/admin/orders/{order_id}/status" in paths
