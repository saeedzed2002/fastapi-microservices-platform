from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KUBERNETES = ROOT / "infrastructure" / "kubernetes"
CONFORMANCE = KUBERNETES / "conformance"
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
DATABASE_SERVICES = SERVICES[1:]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_conformance_has_all_delivery_entrypoints() -> None:
    for entrypoint in ("foundation", "migrations", "workloads", "smoke"):
        document = _read(CONFORMANCE / entrypoint / "kustomization.yaml")
        assert "apiVersion: kustomize.config.k8s.io/v1beta1" in document
        assert "kind: Kustomization" in document


def test_conformance_uses_loaded_images_not_production_registry_credentials() -> None:
    migrations = _read(CONFORMANCE / "migrations" / "kustomization.yaml")
    workloads = _read(CONFORMANCE / "workloads" / "kustomization.yaml")
    smoke = _read(CONFORMANCE / "smoke" / "health-smoke.yaml")

    for service in SERVICES:
        assert f"newName: fastapi-platform/{service}" in workloads
        assert f"fastapi-platform/{service}:conformance" in smoke or service != "reference-service"
    for service in DATABASE_SERVICES:
        assert f"newName: fastapi-platform/{service}" in migrations

    assert "imagePullSecrets" in migrations
    assert "imagePullSecrets" in workloads
    assert "value: []" in migrations
    assert "value: []" in workloads
    assert migrations.count("value: Never") == 1
    assert workloads.count("value: Never") == 2
    assert "ghcr-pull" not in migrations
    assert "ghcr-pull" not in workloads


def test_conformance_dependencies_and_secrets_are_isolated_test_inputs() -> None:
    dependencies = _read(CONFORMANCE / "foundation" / "dependencies.yaml")
    secrets = _read(CONFORMANCE / "foundation" / "runtime-secrets.yaml")

    assert "fastapi-platform-dependencies" in dependencies
    assert 'platform.fastapi.io/conformance: "true"' in dependencies
    assert "image: fastapi-platform/minio:conformance" in dependencies
    assert "imagePullPolicy: Never" in dependencies
    assert "REPLACE" not in secrets
    assert "provider-disabled" in secrets
    assert "smtp://" not in secrets
    assert "fastapi-platform-dependencies.svc.cluster.local" in secrets

    # These values use YAML flow mappings.  Kafka listener values contain
    # commas and colons, so they must remain quoted or Kubernetes will decode
    # their fragments as unknown fields in the Deployment schema.
    for value in (
        "broker,controller",
        "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
        "CONTROLLER://:29093,PLAINTEXT://:9092",
        "PLAINTEXT://kafka.fastapi-platform-dependencies.svc.cluster.local:9092",
        "1@kafka:29093",
    ):
        assert f'value: "{value}"' in dependencies

    for service in DATABASE_SERVICES:
        assert f"CREATE USER {service.replace('-', '_')}" in dependencies


def test_smoke_job_checks_every_api_readiness_endpoint() -> None:
    smoke = _read(CONFORMANCE / "smoke" / "health-smoke.yaml")

    for service in SERVICES:
        assert f'"{service}",' in smoke
    assert "http://{service}/health/ready" in smoke
    assert "runAsNonRoot: true" in smoke
    assert "readOnlyRootFilesystem: true" in smoke


def test_kind_cluster_and_ci_script_are_pinned_and_disposable() -> None:
    kind_config = _read(CONFORMANCE / "kind-config.yaml")
    script = _read(ROOT / "scripts" / "run_kubernetes_conformance.sh")
    workflow = _read(ROOT / ".github" / "workflows" / "platform-ci.yml")

    expected_node_image = (
        "kindest/node:v1.36.1@sha256:"
        "3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
    )
    assert expected_node_image in kind_config
    assert "kind delete cluster" in script
    assert "kind export logs" in script
    assert "platform-health-smoke" in script
    assert script.count("--provenance=false") == 2
    assert 'for image in "${DEPENDENCY_IMAGES[@]}" "fastapi-platform/minio:conformance"' in script
    assert "CONFORMANCE_SKIP_IMAGE_BUILD:-false" in script
    assert '[[ "${SKIP_IMAGE_BUILD}" == "true" ]]' in script
    assert "rollout status deployment --all" not in script
    for deployment in ("postgres", "kafka", "rabbitmq", "redis", "minio", "mailpit"):
        assert f"  {deployment}" in script
    assert "Kubernetes Kind conformance" in workflow
    assert "Install verified Kind v0.32.0" in workflow
    assert "50030de23cf40a18505f20426f6a8506bedf13c6e509244bd1fa9463721b0f54" in workflow
