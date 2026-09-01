# Phase 17 Plan — Portfolio evidence and reviewer guide

## Outcome

Make the completed platform reviewable as a portfolio artifact without
overstating its runtime or delivery scope. A reviewer must be able to trace a
material architectural claim to code, a contract, a runbook, or executable CI
evidence in minutes rather than infer it from a long service list.

## Scope

- a concise reviewer path from the root README;
- an evidence map for service ownership, distributed checkout, durable
  messaging, realtime support, Kubernetes conformance, and container security;
- explicit boundaries between artifact publication, disposable-cluster proof,
  and a target-environment deployment;
- explicit non-goals for the absent storefront, Shipping service, live payment
  credentials, TLS issuer, and production operations.

## Non-goals

- no new API, event, service, dependency, or infrastructure technology;
- no fabricated deployment, availability, payment, compliance, or performance
  claim;
- no license selection, production credential, external account, or target
  environment configuration;
- no change to the single-job scanned `GHCR` publication policy.

## Acceptance evidence

- README links to a reviewer guide and the Phase 17 plan;
- each major platform claim in the guide links to primary in-repository
  evidence;
- local documentation validation verifies every new local link;
- the guide makes clear that immutable image publication and disposable `Kind`
  conformance are not public deployment.
