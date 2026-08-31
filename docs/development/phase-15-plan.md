# Phase 15 Plan — Kubernetes API autoscaling

## Outcome

Make the Kubernetes delivery model honestly capable of bounded horizontal API
scaling, while preserving service ownership and separating HTTP scaling from
queue-worker scaling.

## Scope

- `autoscaling/v2` CPU HPA for every stateless HTTP API Deployment;
- matching raw Kustomize and Helm rendering paths;
- quota sized for the declared HPA envelope and zero-unavailable rollouts;
- disposable Kind metrics-server setup and verification of real HPA CPU
  samples;
- ADR, toolchain evidence, CI documentation, and an operator runbook.

## Non-goals

- queue-driven worker autoscaling, `KEDA`, custom metrics, external metrics,
  or scale-to-zero;
- a production cluster autoscaler, node-pool policy, cloud provider, or
  metrics-server installation;
- synthetic performance certification or production traffic thresholds;
- changes to application APIs, events, databases, migration ownership, or
  Docker Compose development.

## Acceptance evidence

- every API HPA targets its own Deployment and uses an explicit CPU request;
- raw resources and Helm templates have the same bounded policy;
- the disposable Kind cluster exposes `metrics.k8s.io` and each HPA reports a
  current CPU utilization value;
- workers remain outside the CPU HPA model;
- quota, runbook, ADR, rendering, static tests, and CI evidence agree.
