#!/usr/bin/env bash
# Run the Helm delivery proof against a disposable Kind cluster. This script is
# for CI and local verification only; production deployments use immutable
# GHCR digests and the operator runbook instead.
set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CLUSTER_NAME="${KIND_CLUSTER_NAME:-fastapi-platform-conformance}"
readonly SKIP_IMAGE_BUILD="${CONFORMANCE_SKIP_IMAGE_BUILD:-false}"
readonly CONTEXT="kind-${CLUSTER_NAME}"
readonly APP_NAMESPACE="fastapi-platform"
readonly DEPENDENCY_NAMESPACE="fastapi-platform-dependencies"
readonly METRICS_SERVER_RELEASE_URL="https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.0/components.yaml"
readonly METRICS_SERVER_MANIFEST_SHA256="1cec29a5267809306a2c6ec74a3e449abbb705b4a8beed0c8a1963910f72c79b"
readonly METRICS_SERVER_SOURCE_IMAGE="registry.k8s.io/metrics-server/metrics-server@sha256:d9862115e7c7881280d3d75ca26bda8ffc0fc213315979575bf23ce9826205c0"
readonly METRICS_SERVER_LOCAL_IMAGE="fastapi-platform/conformance-metrics-server:local"
readonly SERVICE_IMAGES=(
  reference-service
  identity-service
  customer-service
  catalog-service
  search-service
  media-service
  inventory-service
  cart-service
  order-service
  payment-service
  notification-service
  chat-service
)
readonly API_DEPLOYMENTS=(
  reference-service
  identity-service
  customer-service
  catalog-service
  search-service
  media-service
  inventory-service
  cart-service
  order-service
  payment-service
  notification-service
  chat-service
)
readonly WORKER_DEPLOYMENTS=(
  identity-event-worker
  customer-event-worker
  catalog-event-worker
  search-event-worker
  inventory-event-worker
  order-event-worker
  payment-event-worker
  media-event-worker
  notification-event-worker
  order-invoice-worker
  notification-email-worker
  notification-sms-worker
  media-worker
  payment-expiry-worker
)
readonly DEPENDENCY_DEPLOYMENTS=(
  postgres
  kafka
  rabbitmq
  redis
  minio
  mailpit
)
readonly DEPENDENCY_SOURCE_IMAGES=(
  "postgres:18.6@sha256:1957b2ff3137e4ef7f3bc813e74fff50b1e1ffddc85c8b9d6f14ade972be8687"
  "apache/kafka:4.2.0@sha256:9516fb7634bad307d17c33b589fde9023003b0cb761374f500002b980a3149b9"
  "rabbitmq:4.3.5-management@sha256:06fb591136a49e861e01aaaf9ce45085839ca23c35913d45a1e83519bb9778ca"
  "redis:8.10.0@sha256:344e3945a0b431c8ff1eecd58c5573538126bd756f02fc7e218ddf1fc2546366"
  "axllent/mailpit:v1.30.0@sha256:0059ef81e492a7192af3816281eed6859eb078bd7bdc58b76757c13e10e53a7d"
)
readonly DEPENDENCY_LOCAL_IMAGES=(
  "fastapi-platform/conformance-postgres:local"
  "fastapi-platform/conformance-kafka:local"
  "fastapi-platform/conformance-rabbitmq:local"
  "fastapi-platform/conformance-redis:local"
  "fastapi-platform/conformance-mailpit:local"
)

cluster_created=false

install_metrics_server() {
  local manifest
  manifest="$(mktemp)"

  curl --fail --location --retry 3 --output "${manifest}" "${METRICS_SERVER_RELEASE_URL}"
  echo "${METRICS_SERVER_MANIFEST_SHA256}  ${manifest}" | sha256sum --check

  # Kind's test kubelet certificate is self-signed. This exception is local to
  # the disposable conformance cluster and is never part of delivery charts.
  sed --in-place \
    "s|image: registry.k8s.io/metrics-server/metrics-server:v0.9.0|image: ${METRICS_SERVER_LOCAL_IMAGE}|" \
    "${manifest}"
  sed --in-place \
    '/--kubelet-use-node-status-port/a\\        - --kubelet-insecure-tls' \
    "${manifest}"
  sed --in-place 's/imagePullPolicy: IfNotPresent/imagePullPolicy: Never/' "${manifest}"

  kubectl --context "${CONTEXT}" apply --filename "${manifest}"
  rm --force "${manifest}"
  kubectl --context "${CONTEXT}" -n kube-system rollout status deployment/metrics-server --timeout=5m
  kubectl --context "${CONTEXT}" wait \
    --for=condition=Available apiservice/v1beta1.metrics.k8s.io \
    --timeout=5m
}

wait_for_hpa_metrics() {
  local hpa utilization attempt

  for attempt in {1..24}; do
    if ! kubectl --context "${CONTEXT}" get --raw \
      "/apis/metrics.k8s.io/v1beta1/namespaces/${APP_NAMESPACE}/pods" >/dev/null; then
      sleep 5
      continue
    fi

    for hpa in "${API_DEPLOYMENTS[@]}"; do
      utilization="$(kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" get "horizontalpodautoscaler/${hpa}" \
        --output jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}')"
      if [[ -z "${utilization}" ]]; then
        break
      fi
    done

    if [[ -n "${utilization}" ]]; then
      kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" get horizontalpodautoscaler
      return 0
    fi
    sleep 5
  done

  echo "HPA targets did not receive CPU utilization metrics." >&2
  kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" get horizontalpodautoscaler -o wide || true
  kubectl --context "${CONTEXT}" get apiservice/v1beta1.metrics.k8s.io -o yaml || true
  return 1
}

dump_namespace_logs() {
  local namespace="$1"
  local pod

  kubectl --context "${CONTEXT}" -n "${namespace}" get pods -o name 2>/dev/null |
    while IFS= read -r pod; do
      [[ -n "${pod}" ]] || continue
      echo "--- current logs: ${namespace}/${pod} ---" >&2
      kubectl --context "${CONTEXT}" -n "${namespace}" logs "${pod}" \
        --all-containers=true --prefix --tail=200 || true
      echo "--- previous logs: ${namespace}/${pod} ---" >&2
      kubectl --context "${CONTEXT}" -n "${namespace}" logs "${pod}" \
        --all-containers=true --prefix --previous --tail=200 || true
    done || true
}

diagnose() {
  local exit_code="$?"
  if [[ "${cluster_created}" == true ]]; then
    if [[ "${exit_code}" -ne 0 ]]; then
      echo "Kubernetes conformance failed; collecting diagnostics." >&2
      kubectl --context "${CONTEXT}" get all --all-namespaces || true
      kubectl --context "${CONTEXT}" get events --all-namespaces --sort-by=.lastTimestamp || true
      kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" get pods -o wide || true
      kubectl --context "${CONTEXT}" -n "${DEPENDENCY_NAMESPACE}" get pods -o wide || true
      dump_namespace_logs "${DEPENDENCY_NAMESPACE}"
      dump_namespace_logs "${APP_NAMESPACE}"
      kind export logs --name "${CLUSTER_NAME}" "${ROOT_DIR}/kind-conformance-logs" || true
    fi
    kind delete cluster --name "${CLUSTER_NAME}" || true
  fi
  exit "${exit_code}"
}
trap diagnose EXIT

cd "${ROOT_DIR}"

for command in docker kind kubectl helm; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Kubernetes conformance requires '${command}' on PATH." >&2
    exit 1
  fi
done

if kind get clusters | grep --fixed-strings --line-regexp --quiet "${CLUSTER_NAME}"; then
  echo "Refusing to overwrite existing Kind cluster: ${CLUSTER_NAME}" >&2
  exit 1
fi

if [[ "${SKIP_IMAGE_BUILD}" == "true" ]]; then
  echo "Skipping local image builds; using prebuilt conformance images."
else
  echo "Building service images from the checked-out source revision."
  for service in "${SERVICE_IMAGES[@]}"; do
    docker build \
      --quiet \
      --provenance=false \
      --file "services/${service}/Dockerfile" \
      --tag "fastapi-platform/${service}:conformance" \
      .
  done
  docker build \
    --quiet \
    --provenance=false \
    --file infrastructure/minio/Dockerfile \
    --tag fastapi-platform/minio:conformance \
    infrastructure/minio
  docker build \
    --quiet \
    --provenance=false \
    --file infrastructure/kubernetes/conformance/e2e/Dockerfile \
    --tag fastapi-platform/checkout-e2e:conformance \
    .
fi

echo "Pulling pinned disposable dependency images."
for index in "${!DEPENDENCY_SOURCE_IMAGES[@]}"; do
  source_image="${DEPENDENCY_SOURCE_IMAGES[${index}]}"
  local_image="${DEPENDENCY_LOCAL_IMAGES[${index}]}"
  docker pull "${source_image}"
  docker tag "${source_image}" "${local_image}"
done
docker pull "${METRICS_SERVER_SOURCE_IMAGE}"
docker tag "${METRICS_SERVER_SOURCE_IMAGE}" "${METRICS_SERVER_LOCAL_IMAGE}"

kind create cluster \
  --name "${CLUSTER_NAME}" \
  --config infrastructure/kubernetes/conformance/kind-config.yaml \
  --wait 180s
cluster_created=true

echo "Loading checked-out and locally tagged dependency images into the disposable Kind node."
for image in "${DEPENDENCY_LOCAL_IMAGES[@]}" "${METRICS_SERVER_LOCAL_IMAGE}" "fastapi-platform/minio:conformance" "fastapi-platform/checkout-e2e:conformance"; do
  kind load docker-image --name "${CLUSTER_NAME}" "${image}"
done
for service in "${SERVICE_IMAGES[@]}"; do
  kind load docker-image --name "${CLUSTER_NAME}" "fastapi-platform/${service}:conformance"
done

install_metrics_server

helm --kube-context "${CONTEXT}" upgrade --install platform-foundation \
  infrastructure/helm/fastapi-platform-foundation \
  --namespace "${APP_NAMESPACE}" \
  --create-namespace \
  --values infrastructure/helm/fastapi-platform-foundation/values-conformance.yaml \
  --wait \
  --timeout 5m

kubectl --context "${CONTEXT}" apply -k infrastructure/kubernetes/conformance/foundation
for deployment in "${DEPENDENCY_DEPLOYMENTS[@]}"; do
  kubectl --context "${CONTEXT}" -n "${DEPENDENCY_NAMESPACE}" rollout status "deployment/${deployment}" --timeout=10m
done

helm --kube-context "${CONTEXT}" upgrade --install fastapi-platform \
  infrastructure/helm/fastapi-platform \
  --namespace "${APP_NAMESPACE}" \
  --values infrastructure/helm/fastapi-platform/values-conformance.yaml \
  --wait \
  --wait-for-jobs \
  --timeout 10m

kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" wait \
  --for=condition=complete \
  job \
  --selector=platform.fastapi.io/workload=migration \
  --timeout=10m

for deployment in "${API_DEPLOYMENTS[@]}" "${WORKER_DEPLOYMENTS[@]}"; do
  kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" rollout status "deployment/${deployment}" --timeout=10m
done
wait_for_hpa_metrics

kubectl --context "${CONTEXT}" apply -k infrastructure/kubernetes/conformance/smoke
kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" wait --for=condition=complete job/platform-health-smoke --timeout=5m
kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" logs job/platform-health-smoke
kubectl --context "${CONTEXT}" apply -k infrastructure/kubernetes/conformance/e2e
kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" wait --for=condition=complete job/platform-checkout-e2e --timeout=6m
kubectl --context "${CONTEXT}" -n "${APP_NAMESPACE}" logs job/platform-checkout-e2e
echo "Kubernetes conformance completed successfully."
