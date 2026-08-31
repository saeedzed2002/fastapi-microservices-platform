from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KUBERNETES = ROOT / "infrastructure" / "kubernetes"
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
METRICS_SERVER_DIGEST = "d9862115e7c7881280d3d75ca26bda8ffc0fc213315979575bf23ce9826205c0"
METRICS_SERVER_MANIFEST_SHA256 = "1cec29a5267809306a2c6ec74a3e449abbb705b4a8beed0c8a1963910f72c79b"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_raw_kubernetes_hpas_cover_only_the_stateless_http_apis() -> None:
    workloads = _read(KUBERNETES / "workloads" / "kustomization.yaml")
    autoscaling = _read(KUBERNETES / "workloads" / "autoscaling.yaml")
    background = _read(KUBERNETES / "workloads" / "background-workloads.yaml")

    assert "autoscaling.yaml" in workloads
    assert autoscaling.count("kind: HorizontalPodAutoscaler") == len(SERVICES)
    assert autoscaling.count("apiVersion: autoscaling/v2") == len(SERVICES)
    assert autoscaling.count("minReplicas: 2") == len(SERVICES)
    assert autoscaling.count("maxReplicas: 4") == len(SERVICES)
    assert autoscaling.count("averageUtilization: 70") == len(SERVICES)
    assert autoscaling.count("stabilizationWindowSeconds: 300") == len(SERVICES)

    for service in SERVICES:
        assert f"name: {service}" in autoscaling
        assert f"name: {service}}}" in autoscaling

    assert "HorizontalPodAutoscaler" not in background
    assert "payment-expiry-worker" not in autoscaling


def test_helm_exposes_bounded_cpu_hpas_and_one_node_conformance_override() -> None:
    values = _read(HELM / "fastapi-platform" / "values.yaml")
    conformance_values = _read(HELM / "fastapi-platform" / "values-conformance.yaml")
    foundation_values = _read(HELM / "fastapi-platform-foundation" / "values.yaml")
    api_workloads = _read(HELM / "fastapi-platform" / "templates" / "api-workloads.yaml")
    autoscaling = _read(HELM / "fastapi-platform" / "templates" / "autoscaling.yaml")

    assert "enabled: true" in values
    assert "minReplicas: 2" in values
    assert "maxReplicas: 4" in values
    assert "targetCPUUtilizationPercentage: 70" in values
    assert "stabilizationWindowSeconds: 300" in values
    assert "minReplicas: 1" in conformance_values
    assert "maxReplicas: 1" in conformance_values
    assert "kind: HorizontalPodAutoscaler" in autoscaling
    assert "apiVersion: autoscaling/v2" in autoscaling
    assert "range $name, $_ := .Values.apiServices" in autoscaling
    assert (
        "averageUtilization: {{ $.Values.autoscaling.targetCPUUtilizationPercentage }}"
        in autoscaling
    )
    assert "scaleTargetRef:" in autoscaling
    assert "ternary $.Values.autoscaling.minReplicas" in api_workloads
    for quota_value in (
        'pods: "75"',
        'requestsCpu: "12"',
        "requestsMemory: 24Gi",
        'limitsCpu: "72"',
        "limitsMemory: 36Gi",
    ):
        assert quota_value in foundation_values


def test_kind_conformance_pins_metrics_server_and_requires_hpa_metric_samples() -> None:
    script = _read(ROOT / "scripts" / "run_kubernetes_conformance.sh")

    assert "metrics-server/releases/download/v0.9.0/components.yaml" in script
    assert METRICS_SERVER_MANIFEST_SHA256 in script
    assert METRICS_SERVER_DIGEST in script
    assert "METRICS_SERVER_LOCAL_IMAGE" in script
    assert "install_metrics_server" in script
    assert "--kubelet-insecure-tls" in script
    assert "apiservice/v1beta1.metrics.k8s.io" in script
    assert "wait_for_hpa_metrics" in script
    assert "/apis/metrics.k8s.io/v1beta1/namespaces/${APP_NAMESPACE}/pods" in script
    assert "horizontalpodautoscaler/${hpa}" in script
