from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KUBERNETES = ROOT / "infrastructure" / "kubernetes"
DATABASE_SERVICES = (
    "identity-service",
    "customer-service",
    "catalog-service",
    "search-service",
    "media-service",
    "inventory-service",
    "cart-service",
    "order-service",
    "payment-service",
    "notification-service",
    "chat-service",
)
ENVIRONMENT_KEYS = (
    "IDENTITY_ENVIRONMENT",
    "CUSTOMER_ENVIRONMENT",
    "CATALOG_ENVIRONMENT",
    "SEARCH_ENVIRONMENT",
    "MEDIA_ENVIRONMENT",
    "INVENTORY_ENVIRONMENT",
    "CART_ENVIRONMENT",
    "ORDER_ENVIRONMENT",
    "PAYMENT_ENVIRONMENT",
    "NOTIFICATION_ENVIRONMENT",
    "CHAT_ENVIRONMENT",
)
DIGEST_PLACEHOLDER = "sha256:" + "0" * 64


def _read(*parts: str) -> str:
    return (KUBERNETES.joinpath(*parts)).read_text(encoding="utf-8")


def test_kubernetes_kustomize_entrypoints_have_explicit_resources() -> None:
    for entrypoint in ("foundation", "migrations", "workloads"):
        document = _read(entrypoint, "kustomization.yaml")
        assert "apiVersion: kustomize.config.k8s.io/v1beta1" in document
        assert "kind: Kustomization" in document
        assert "resources:" in document


def test_workloads_are_digest_pinned_and_have_no_mutable_tag() -> None:
    documents = (
        _read("workloads", "api-workloads.yaml"),
        _read("workloads", "background-workloads.yaml"),
        _read("migrations", "migration-jobs.yaml"),
    )
    images = re.findall(r"image: (ghcr\.io/[^\s]+)", "\n".join(documents))

    assert len(images) == 29
    assert all(f"@{DIGEST_PLACEHOLDER}" in image for image in images)
    assert all(":latest" not in image for image in images)


def test_database_migrations_are_controlled_jobs_and_ship_their_sources() -> None:
    migrations = _read("migrations", "migration-jobs.yaml")

    assert migrations.count("kind: Job") == len(DATABASE_SERVICES)
    assert "generateName:" not in migrations
    assert migrations.count("platform.fastapi.io/workload: migration") == 2 * len(DATABASE_SERVICES)
    assert migrations.count("command: [alembic, -c, /app/alembic.ini, upgrade, head]") == len(
        DATABASE_SERVICES
    )

    for service in DATABASE_SERVICES:
        dockerfile = (ROOT / "services" / service / "Dockerfile").read_text(encoding="utf-8")
        assert f"COPY services/{service}/migrations ./migrations" in dockerfile
        assert f"COPY services/{service}/alembic.ini ./alembic.ini" in dockerfile


def test_runtime_config_sets_each_service_environment_explicitly() -> None:
    runtime_config = _read("foundation", "runtime-config.yaml")

    for key in ENVIRONMENT_KEYS:
        assert f"  {key}: production" in runtime_config

    for key in (
        "MEDIA_S3_BUCKET: fastapi-platform-media",
        "ORDER_S3_BUCKET: fastapi-platform-invoices",
        'NOTIFICATION_SMTP_PORT: "587"',
    ):
        assert f"  {key}" in runtime_config


def test_resource_quota_allows_the_zero_unavailable_rolling_update_budget() -> None:
    resource_policy = _read("foundation", "resource-policy.yaml")

    assert 'pods: "50"' in resource_policy
    assert 'requests.cpu: "6"' in resource_policy
    assert "requests.memory: 12Gi" in resource_policy
    assert 'limits.cpu: "48"' in resource_policy
    assert "limits.memory: 24Gi" in resource_policy


def test_secret_template_is_not_in_the_foundation_apply_set() -> None:
    foundation = _read("foundation", "kustomization.yaml")
    secret_template = _read("foundation", "runtime-secrets.example.yaml")

    assert "runtime-secrets.example.yaml" not in foundation
    assert "REPLACE" in secret_template
