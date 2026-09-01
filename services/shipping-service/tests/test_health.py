from shipping_service.main import app


def test_shipping_openapi_exposes_no_shipment_mutation_before_transition_fence() -> None:
    paths = app.openapi()["paths"]
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert not any("shipment" in path for path in paths)
