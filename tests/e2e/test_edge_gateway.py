import os
import socket

import httpx
import pytest

pytestmark = pytest.mark.e2e


LOCAL_DOCS = {
    "reference": "Reference Service",
    "identity": "Identity Service",
    "customer": "Customer Service",
    "catalog": "Catalog Service",
    "media": "Media Service",
    "inventory": "Inventory Service",
    "cart": "Cart Service",
    "order": "Order Service",
    "payment": "Payment Service",
    "search": "Search Service",
    "notification": "Notification Service",
    "chat": "Chat Service",
}


def test_edge_routes_tls_headers_and_sensitive_rate_limit() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    base_url = os.environ.get("E2E_BASE_URL", "https://localhost")
    with httpx.Client(verify=False, follow_redirects=False, timeout=10.0) as client:
        ready = client.get(f"{base_url}/health/ready")
        ready.raise_for_status()
        assert ready.text == "ok"
        assert ready.headers["strict-transport-security"] == "max-age=31536000"
        assert ready.headers["x-content-type-options"] == "nosniff"
        assert ready.headers["x-frame-options"] == "DENY"
        assert ready.headers["referrer-policy"] == "no-referrer"

        root = client.get(base_url)
        root.raise_for_status()
        assert root.json() == {"status": "ok", "api_base": "/api/v1"}

        redirect = client.get("http://127.0.0.1/api/v1/reference")
        assert redirect.status_code == 308
        assert redirect.headers["location"] == "https://localhost/api/v1/reference"

        reference = client.get(f"{base_url}/api/v1/reference")
        reference.raise_for_status()
        assert reference.headers["x-request-id"]

        internal = client.get(f"{base_url}/api/internal/v1/media/assets")
        assert internal.status_code == 404

        responses = [client.post(f"{base_url}/api/v1/auth/login", json={}) for _ in range(12)]
        assert responses[-1].status_code == 429

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as direct_api_socket:
        direct_api_socket.settimeout(1.0)
        assert direct_api_socket.connect_ex(("127.0.0.1", 8001)) != 0


def test_edge_exposes_local_swagger_for_each_service() -> None:
    if os.environ.get("RUN_E2E") != "1":
        pytest.skip("set RUN_E2E=1 after starting the local Docker Compose platform")

    base_url = os.environ.get("E2E_BASE_URL", "https://localhost")
    with httpx.Client(verify=False, timeout=10.0) as client:
        index = client.get(f"{base_url}/docs/")
        index.raise_for_status()
        assert "Local API documentation" in index.text

        for service, title in LOCAL_DOCS.items():
            docs = client.get(f"{base_url}/docs/{service}")
            docs.raise_for_status()
            assert f"url: '/docs/{service}/openapi.json'" in docs.text

            openapi = client.get(f"{base_url}/docs/{service}/openapi.json")
            openapi.raise_for_status()
            assert openapi.json()["info"]["title"] == title
