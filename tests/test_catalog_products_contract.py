import json
from pathlib import Path


def test_catalog_product_list_contract_is_catalogued() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "contracts" / "catalog.json").read_text(encoding="utf-8"))
    contracts = {contract["name"]: contract for contract in catalog["contracts"]}

    contract = contracts["catalog.products.v1"]
    assert contract["owner"] == "catalog-service"
    assert contract["status"] == "active"
    document = json.loads((root / "contracts" / contract["schema"]).read_text(encoding="utf-8"))
    assert document["paths"]["/api/v1/catalog/products"]["get"]["parameters"][0]["name"] == "limit"
