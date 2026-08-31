from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELM = ROOT / "infrastructure" / "helm"
SERVICES = (
    "reference-service",
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
DATABASE_MIGRATIONS = (
    "identity",
    "customer",
    "catalog",
    "search",
    "media",
    "inventory",
    "cart",
    "order",
    "payment",
    "notification",
    "chat",
)
HELM_SHA256 = "c306b46f719b0a4da32d0f78ee21bf90ce8d602f15b22ab753f0674d1670a7f3"


def _read(*parts: str) -> str:
    return HELM.joinpath(*parts).read_text(encoding="utf-8")


def test_helm_charts_preserve_the_foundation_application_boundary() -> None:
    foundation_chart = _read("fastapi-platform-foundation", "Chart.yaml")
    application_chart = _read("fastapi-platform", "Chart.yaml")
    foundation_templates = _read("fastapi-platform-foundation", "templates", "runtime-config.yaml")
    application_values = _read("fastapi-platform", "values.yaml")

    assert "apiVersion: v2" in foundation_chart
    assert 'kubeVersion: ">=1.36.0-0"' in foundation_chart
    assert "apiVersion: v2" in application_chart
    assert 'kubeVersion: ">=1.36.0-0"' in application_chart
    assert "kind: Namespace" not in foundation_templates
    assert "tpl (toString $value) $" in foundation_templates
    assert "configMapName: platform-runtime-config" in application_values
    assert "secretName: platform-runtime-secrets" in application_values


def test_delivery_images_require_digests_and_conformance_tags_are_explicit() -> None:
    values = _read("fastapi-platform", "values.yaml")
    helper = _read("fastapi-platform", "templates", "_helpers.tpl")
    conformance_values = _read("fastapi-platform", "values-conformance.yaml")

    assert "allowMutableTags: false" in values
    assert "allowMutableTags: true" in conformance_values
    assert "@sha256:%s" in helper
    assert "must contain exactly 64 lowercase hexadecimal characters" in helper
    assert "tag is forbidden; use an immutable digest for delivery" in helper
    assert "pullPolicy: Never" in conformance_values
    assert "pullSecrets: []" in conformance_values

    for service in SERVICES:
        assert f"{service}: {{digest:" in values
        assert f"{service}: {{tag: conformance}}" in conformance_values


def test_application_chart_retains_every_workload_and_controlled_migration() -> None:
    values = _read("fastapi-platform", "values.yaml")
    api_workloads = _read("fastapi-platform", "templates", "api-workloads.yaml")
    migrations = _read("fastapi-platform", "templates", "migration-jobs.yaml")
    background = _read("fastapi-platform", "templates", "background-workloads.yaml")
    availability = _read("fastapi-platform", "templates", "availability.yaml")
    helpers = _read("fastapi-platform", "templates", "_helpers.tpl")

    for service in SERVICES:
        assert f"{service}:" in values
    for migration in DATABASE_MIGRATIONS:
        assert f"name: {migration}, image:" in values

    assert "replicas: {{ $.Values.api.replicas }}" in api_workloads
    assert "readOnlyRootFilesystem: true" in helpers
    assert "platform.fastapi.io/workload: api" in api_workloads
    assert "helm.sh/hook: pre-install,pre-upgrade" in migrations
    assert "helm.sh/hook-delete-policy: before-hook-creation" in migrations
    assert "command: [alembic, -c, /app/alembic.ini, upgrade, head]" in migrations
    assert "platform.fastapi.io/workload: migration" in migrations
    assert "payment-expiry-worker" in values
    assert "media-upload-reaper" in values
    assert 'include "fastapi-platform.containerSecurityContext"' in background
    assert "minAvailable: 1" in availability


def test_kind_conformance_installs_charts_and_ci_pins_helm() -> None:
    script = (ROOT / "scripts" / "run_kubernetes_conformance.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "platform-ci.yml").read_text(encoding="utf-8")
    harness = (
        ROOT / "infrastructure" / "kubernetes" / "conformance" / "foundation" / "kustomization.yaml"
    ).read_text(encoding="utf-8")

    assert "docker kind kubectl helm" in script
    assert "platform-foundation" in script
    assert "infrastructure/helm/fastapi-platform-foundation" in script
    assert "infrastructure/helm/fastapi-platform" in script
    assert "--wait-for-jobs" in script
    assert "apply -k infrastructure/kubernetes/conformance/migrations" not in script
    assert "apply -k infrastructure/kubernetes/conformance/workloads" not in script
    assert "../../foundation" not in harness
    assert "runtime-secrets.yaml" in harness
    assert "dependencies.yaml" in harness
    assert workflow.count("Install verified Helm v4.2.4") == 2
    assert workflow.count(HELM_SHA256) == 2
    assert "helm lint infrastructure/helm/fastapi-platform --strict" in workflow
    assert "The delivery chart rendered without immutable image digests." in workflow
    assert 'grep --fixed-strings "immutable release digest"' in workflow
