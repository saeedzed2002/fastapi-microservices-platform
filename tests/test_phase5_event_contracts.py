import json
from pathlib import Path


def test_phase5_emitted_events_are_active_and_have_schemas() -> None:
    root = Path(__file__).parents[1]
    catalog = json.loads((root / "contracts" / "catalog.json").read_text(encoding="utf-8"))
    contracts = {contract["name"]: contract for contract in catalog["contracts"]}

    for event_name in (
        "order.created.v1",
        "inventory.reserved.v1",
        "inventory.reservation_failed.v1",
        "payment.processing.v1",
        "payment.succeeded.v1",
        "payment.failed.v1",
        "order.confirmed.v1",
        "invoice.generated.v1",
    ):
        contract = contracts[event_name]
        assert contract["status"] == "active"
        assert contract["message_key"] == "order_id"
        assert (root / "contracts" / contract["schema"]).is_file()
