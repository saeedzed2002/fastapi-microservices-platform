import json
from pathlib import Path


def test_zarinpal_payment_is_exposed_only_through_the_edge() -> None:
    root = Path(__file__).resolve().parents[1]
    edge = (root / "infrastructure" / "edge" / "nginx.conf").read_text(encoding="utf-8")
    compose = (root / "infrastructure" / "compose" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert "location ^~ /api/v1/payments/" in edge
    assert "proxy_pass http://$payment_upstream;" in edge
    assert "PAYMENT_ORDER_BASE_URL: http://order-service:8000" in compose
    assert 'PAYMENT_EXPIRY_WORKER_ENABLED: "true"' in compose


def test_zarinpal_callback_uses_the_edge_payment_route() -> None:
    root = Path(__file__).resolve().parents[1]
    example = (root / ".env.example").read_text(encoding="utf-8")

    assert "ZARINPAL_CALLBACK_URL=https://localhost/api/v1/payments/zarinpal/callback" in example
    assert "ORDER_PAYMENT_RESERVATION_MINUTES" not in example


def test_zarinpal_openapi_contract_is_catalogued() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "contracts" / "catalog.json").read_text(encoding="utf-8"))
    contracts = {contract["name"]: contract for contract in catalog["contracts"]}

    contract = contracts["payment.zarinpal.v1"]
    assert contract["owner"] == "payment-service"
    assert contract["status"] == "active"
    assert contract["schema"] == "openapi/payment-zarinpal.v1.openapi.json"
    assert (root / "contracts" / contract["schema"]).is_file()
