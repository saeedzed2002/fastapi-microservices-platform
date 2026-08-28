from pathlib import Path


def test_local_edge_resolves_compose_service_upstreams_at_request_time() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "infrastructure" / "edge" / "nginx.conf").read_text(encoding="utf-8")

    assert "resolver 127.0.0.11 valid=10s ipv6=off;" in config
    for service in (
        "reference-service",
        "identity-service",
        "customer-service",
        "catalog-service",
        "media-service",
        "inventory-service",
        "cart-service",
        "order-service",
        "payment-service",
        "notification-service",
        "chat-service",
    ):
        assert f"proxy_pass http://{service}:8000" not in config

    for upstream in (
        "reference_upstream",
        "identity_upstream",
        "customer_upstream",
        "catalog_upstream",
        "media_upstream",
        "inventory_upstream",
        "cart_upstream",
        "order_upstream",
        "payment_upstream",
        "notification_upstream",
        "chat_upstream",
    ):
        assert f"set ${upstream} " in config
        assert f"proxy_pass http://${upstream}" in config
