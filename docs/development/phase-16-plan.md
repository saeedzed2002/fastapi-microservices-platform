# Phase 16 Plan — Online payment provider routing

## Outcome

Provide a customer-facing online payment route with a second provider while
preserving Payment ownership, durable attempt evidence, and strict protection
against duplicate external payment requests.

## Scope

- additive `online` checkout and Payment APIs;
- Payment-owned Zarinpal-first routing with Zibal fallback after a definitive
  primary rejection only;
- direct Zibal request, redirect, and server-side verification adapter using
  the locked `HTTPX` dependency;
- expiry coverage for routed intents and Zarinpal reversal compatibility for
  routed payments actually settled by Zarinpal;
- Compose, Kubernetes, Helm, contracts, ADR, service documentation, and
  recovery runbook updates;
- unit evidence for safe fallback and unknown-outcome non-fallback behavior.

## Non-goals

- health-check-driven failover, automatic retry after a timeout, or any policy
  that can create duplicate payable transactions;
- a third provider, payment orchestration framework, frontend, or client-side
  provider selection;
- Zibal full or partial refunds, settlement reporting, or a fabricated refund
  success;
- live provider credentials, deployment, or a claim that a real merchant
  transaction ran in local or CI infrastructure.

## Acceptance evidence

- `online` orders produce Payment-owned provider attempts and unchanged Saga
  facts;
- a known Zarinpal rejection is persisted before one Zibal attempt begins;
- a Zarinpal timeout leaves only the durable `REQUESTING` attempt and does not
  call Zibal;
- browser returns are verified against stored provider tokens before success;
- existing Zarinpal endpoints remain compatible and the delivery manifests
  expose no credential values.
