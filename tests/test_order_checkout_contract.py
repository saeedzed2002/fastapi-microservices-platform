import json
from pathlib import Path


def test_order_checkout_openapi_contract_is_catalogued() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "contracts" / "catalog.json").read_text(encoding="utf-8"))
    contracts = {contract["name"]: contract for contract in catalog["contracts"]}

    contract = contracts["order.checkout.v1"]
    assert contract["owner"] == "order-service"
    assert contract["status"] == "active"
    document = json.loads((root / "contracts" / contract["schema"]).read_text(encoding="utf-8"))
    assert "/api/v1/orders/cart/zarinpal" in document["paths"]
    assert "503" in document["paths"]["/api/v1/orders/cart/zarinpal"]["post"]["responses"]
