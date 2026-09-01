from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase19_return_contracts_define_physical_and_financial_boundaries() -> None:
    catalog = json.loads((ROOT / "contracts" / "catalog.json").read_text(encoding="utf-8"))
    contracts = {contract["name"]: contract for contract in catalog["contracts"]}
    receipt_schema = json.loads(
        (ROOT / "contracts" / "events" / "order.return_received.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    returns_api = json.loads(
        (ROOT / "contracts" / "openapi" / "order-returns.v1.openapi.json").read_text(
            encoding="utf-8"
        )
    )

    assert contracts["order.returns.v1"]["status"] == "proposed"
    assert contracts["order.returns.v1"]["owner"] == "order-service"
    assert contracts["order.return_received.v1"]["status"] == "proposed"
    assert contracts["order.return_received.v1"]["consumers"] == ["inventory-service"]
    assert receipt_schema["required"] == ["return_request_id", "order_id", "received_by", "items"]
    assert set(receipt_schema["properties"]["items"]["items"]["required"]) == {"sku", "quantity"}
    assert "/api/v1/orders/{order_id}/returns" in returns_api["paths"]
    assert "/api/v1/orders/admin/returns/{return_request_id}/receipt" in returns_api["paths"]
