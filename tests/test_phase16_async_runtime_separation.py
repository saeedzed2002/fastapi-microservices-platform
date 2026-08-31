from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KUBERNETES = ROOT / "infrastructure" / "kubernetes"
HELM = ROOT / "infrastructure" / "helm"

EVENT_WORKERS = {
    "identity-event-worker": (
        "identity_service.workers.runtime_main",
        ("IDENTITY_KAFKA_PUBLISHER_ENABLED",),
    ),
    "customer-event-worker": (
        "customer_service.workers.runtime_main",
        ("CUSTOMER_KAFKA_CONSUMER_ENABLED",),
    ),
    "catalog-event-worker": (
        "catalog_service.workers.runtime_main",
        ("CATALOG_KAFKA_PUBLISHER_ENABLED",),
    ),
    "search-event-worker": (
        "search_service.workers.runtime_main",
        ("SEARCH_KAFKA_CONSUMER_ENABLED",),
    ),
    "inventory-event-worker": (
        "inventory_service.workers.runtime_main",
        ("INVENTORY_KAFKA_PUBLISHER_ENABLED", "INVENTORY_KAFKA_CONSUMER_ENABLED"),
    ),
    "order-event-worker": (
        "order_service.workers.runtime_main",
        (
            "ORDER_KAFKA_PUBLISHER_ENABLED",
            "ORDER_KAFKA_CONSUMER_ENABLED",
            "ORDER_INVOICE_CONSUMER_ENABLED",
            "ORDER_TASK_DISPATCHER_ENABLED",
        ),
    ),
    "payment-event-worker": (
        "payment_service.workers.runtime_main",
        ("PAYMENT_KAFKA_PUBLISHER_ENABLED", "PAYMENT_KAFKA_CONSUMER_ENABLED"),
    ),
    "media-event-worker": (
        "media_service.workers.runtime_main",
        ("MEDIA_KAFKA_PUBLISHER_ENABLED", "MEDIA_TASK_DISPATCHER_ENABLED"),
    ),
    "notification-event-worker": (
        "notification_service.workers.runtime_main",
        ("NOTIFICATION_KAFKA_CONSUMER_ENABLED", "NOTIFICATION_TASK_DISPATCHER_ENABLED"),
    ),
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_kubernetes_api_defaults_disable_async_loops_and_event_workers_enable_them() -> None:
    raw_runtime = _read(KUBERNETES / "foundation" / "runtime-config.yaml")
    helm_runtime = _read(HELM / "fastapi-platform-foundation" / "values.yaml")
    kustomization = _read(KUBERNETES / "workloads" / "kustomization.yaml")
    raw_workers = _read(KUBERNETES / "workloads" / "event-workloads.yaml")
    helm_values = _read(HELM / "fastapi-platform" / "values.yaml")
    helm_template = _read(HELM / "fastapi-platform" / "templates" / "background-workloads.yaml")

    assert "event-workloads.yaml" in kustomization
    assert "{{- with $worker.env }}" in helm_template
    assert "{{ $value | quote }}" in helm_template

    for worker, (module, flags) in EVENT_WORKERS.items():
        assert f"name: {worker}" in raw_workers
        assert f"-m, {module}" in raw_workers
        assert f"  {worker}:" in helm_values
        assert module in helm_values
        for flag in flags:
            assert f'{flag}: "false"' in raw_runtime
            assert f'{flag}: "false"' in helm_runtime
            assert f'{flag}, value: "true"' in raw_workers
            assert f'{flag}: "true"' in helm_values


def test_event_worker_entrypoints_and_kind_conformance_coverage_exist() -> None:
    conformance = _read(ROOT / "scripts" / "run_kubernetes_conformance.sh")

    for worker, (module, _) in EVENT_WORKERS.items():
        service = module.split(".", maxsplit=1)[0].replace("_", "-")
        entrypoint = (
            ROOT
            / "services"
            / service
            / "src"
            / service.replace("-", "_")
            / "workers"
            / "runtime_main.py"
        )
        assert entrypoint.is_file()
        entrypoint_source = _read(entrypoint)
        assert "run_background_process" in entrypoint_source
        assert "settings." in entrypoint_source
        assert f"  {worker}" in conformance
