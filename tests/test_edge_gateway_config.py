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
        "shipping-service",
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
        "shipping_upstream",
        "notification_upstream",
        "chat_upstream",
    ):
        assert f"set ${upstream} " in config
        assert f"proxy_pass http://${upstream}" in config


def test_local_edge_routes_identity_staff_operations() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "infrastructure" / "edge" / "nginx.conf").read_text(encoding="utf-8")

    assert "location ^~ /api/v1/admin/" in config
    assert "proxy_pass http://$identity_upstream;" in config


def test_local_edge_routes_shipping_administration() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "infrastructure" / "edge" / "nginx.conf").read_text(encoding="utf-8")

    assert "location ^~ /api/v1/shipping/" in config
    assert "proxy_pass http://$shipping_upstream;" in config
    assert "location = /docs/shipping" in config


def test_local_edge_keeps_websocket_and_login_rate_buckets_separate() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "infrastructure" / "edge" / "nginx.conf").read_text(encoding="utf-8")

    assert "zone=edge_sensitive:10m rate=5r/m;" in config
    assert "zone=edge_websocket:10m rate=10r/m;" in config
    websocket_location = config.split("location = /api/v1/chat/ws {", maxsplit=1)[1].split(
        "\n        }", maxsplit=1
    )[0]
    assert "limit_req zone=edge_websocket burst=20 nodelay;" in websocket_location
    assert "limit_req zone=edge_sensitive" not in websocket_location
