# Kubernetes API autoscaling

## Detection

Inspect HPA conditions and the resource Metrics API whenever API latency or
pending requests rise, a Deployment does not grow under CPU pressure, or Pods
remain pending after HPA recommends more replicas.

```bash
kubectl -n fastapi-platform get horizontalpodautoscaler
kubectl -n fastapi-platform describe horizontalpodautoscaler <api-service>
kubectl get --raw /apis/metrics.k8s.io/v1beta1/namespaces/fastapi-platform/pods
kubectl -n fastapi-platform get pods -o wide
kubectl get events --all-namespaces --sort-by=.lastTimestamp
```

## Impact

An unavailable `metrics.k8s.io` API freezes CPU-driven scaling at the current
replica count. A scheduling or quota failure can leave the HPA recommendation
above the number of running Pods. HPA cannot add nodes; exhausted cluster
capacity needs an environment-owned node-autoscaling or capacity response.

## Immediate checks

1. Confirm that the target environment supplies `metrics.k8s.io/v1beta1` and
   that its metrics-server or equivalent component is healthy.
2. Read the HPA `Conditions` and `Events`; distinguish missing metrics from
   `FailedScheduling`, `ResourceQuota`, image, readiness, or database errors.
3. Compare the HPA desired replicas with the Deployment, ReplicaSet, ready Pod
   count, namespace quota, and allocatable node resources.
4. Confirm the affected API container still has an explicit CPU request. CPU
   utilization HPA cannot calculate a percentage without it.

```bash
kubectl -n fastapi-platform get deployment <api-service> \
  -o jsonpath='{.spec.replicas}{" desired, "}{.status.availableReplicas}{" available\n"}'
kubectl -n fastapi-platform get resourcequota platform-workload-budget
kubectl describe node <node-name>
```

## Safe mitigation

- Restore the Metrics API or cluster capacity before changing the HPA policy.
- Investigate the upstream dependency or readiness failure before increasing
  replicas; more Pods do not repair a saturated database, broker, payment
  provider, or broken migration.
- For a temporary controlled incident override, change the HPA minimum or
  maximum through the reviewed Helm release values, record the reason and
  expiry, then restore the approved policy. Do not use `kubectl scale` against
  an HPA-managed Deployment because the controller will overwrite it.
- Do not copy Kind's `--kubelet-insecure-tls` exception into a real cluster.

## Recovery and verification

1. Restore the target environment's metrics component and node capacity.
2. Reapply the approved chart values through the normal Helm release process.
3. Verify every HPA has current CPU utilization and no failed conditions.
4. Verify API readiness, critical checkout behavior, and downstream resource
   saturation before declaring recovery.

```bash
kubectl -n fastapi-platform get horizontalpodautoscaler
kubectl -n fastapi-platform rollout status deployment --timeout=10m
kubectl -n fastapi-platform get pods,services,pdb
```

## Escalation and follow-up

Escalate to the environment owner when `metrics.k8s.io` is absent, node capacity
is exhausted, or the safe maximum is unknown. Record the Git revision, image
digests, HPA conditions, desired/current replicas, quota, node capacity,
workload evidence, and any temporary override. A queue-worker scaling proposal
must select its queue metric, idempotency limits, and controller separately;
it is not an HPA CPU tuning change.
