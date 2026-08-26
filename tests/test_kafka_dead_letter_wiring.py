DEAD_LETTER_TOPIC = "fastapi-platform.dead-letter.v1"
CONSUMER_WORKERS = {
    "services/customer-service/src/customer_service/workers/identity_consumer.py": 1,
    "services/inventory-service/src/inventory_service/workers/kafka.py": 1,
    "services/notification-service/src/notification_service/workers/kafka.py": 1,
    "services/order-service/src/order_service/workers/kafka.py": 2,
    "services/payment-service/src/payment_service/workers/kafka.py": 1,
}
CONSUMER_CONFIGS = [
    "services/customer-service/src/customer_service/config.py",
    "services/inventory-service/src/inventory_service/config.py",
    "services/notification-service/src/notification_service/config.py",
    "services/order-service/src/order_service/config.py",
    "services/payment-service/src/payment_service/config.py",
]


def _repository_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[1]


def test_active_kafka_consumers_use_the_shared_dead_letter_policy() -> None:
    expected_import = (
        "from platform_messaging import KafkaDlqPolicy, process_record_with_dead_letter"
    )
    repository_root = _repository_root()

    for worker_path, consumer_count in CONSUMER_WORKERS.items():
        worker_source = (repository_root / worker_path).read_text(encoding="utf-8")

        assert expected_import in worker_source
        assert worker_source.count("await process_record_with_dead_letter(") == consumer_count
        assert worker_source.count("KafkaDlqPolicy(") == consumer_count


def test_active_kafka_consumers_share_safe_dead_letter_defaults() -> None:
    expected_topic = f'kafka_dead_letter_topic: str = "{DEAD_LETTER_TOPIC}"'
    expected_attempts = "kafka_consumer_max_attempts: int = Field(default=3, ge=1, le=20)"
    expected_backoff = (
        "kafka_consumer_retry_backoff_seconds: float = Field(default=0.25, ge=0.05, le=60.0)"
    )
    repository_root = _repository_root()

    for config_path in CONSUMER_CONFIGS:
        config_source = (repository_root / config_path).read_text(encoding="utf-8")

        assert expected_topic in config_source
        assert expected_attempts in config_source
        assert expected_backoff in config_source
