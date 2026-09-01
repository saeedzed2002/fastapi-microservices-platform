from pathlib import Path


def test_shipping_consumer_is_a_separate_background_entrypoint() -> None:
    service_root = Path(__file__).resolve().parents[1]
    api_source = (service_root / "src/shipping_service/main.py").read_text(encoding="utf-8")
    worker_source = (service_root / "src/shipping_service/workers/runtime_main.py").read_text(
        encoding="utf-8"
    )

    assert "consume_order_events" not in api_source
    assert "consume_order_events" in worker_source
