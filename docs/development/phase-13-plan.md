# Phase 13 Plan — Staff credential recovery and device sessions

## Outcome

Close the Identity lifecycle gap for existing `admin` accounts without changing
the passwordless customer authentication policy. The result is a reviewed,
durable password-reset flow and user-controlled active-session revocation.

## Scope

- non-enumerating reset requests for active password-bearing `admin` users;
- short-lived raw reset delivery state in Identity Redis and hashed persistent
  reset records in Identity PostgreSQL;
- authenticated Identity-to-Notification handoff, durable email task intent,
  and just-in-time token retrieval by the Notification worker;
- password update, one-time consumption, audit record, and all-session
  revocation in one local Identity transaction;
- active-session listing, individual ownership-checked revocation, all-session
  revocation, bounded user-agent metadata, and hashed peer-address metadata;
- verified refresh-token reuse containment at the session-family level;
- migrations, public contract, runtime secret/config examples, tests, and an
  operator runbook.

## Non-goals

- customer password registration or password recovery;
- an access-token denylist or immediate JWT revocation;
- raw IP storage, device geolocation, browser fingerprinting, or a claim that
  an access token identifies its current refresh session;
- a new notification transport, public-email provider integration, or a second
  staff role;
- deploying a public environment. The repository remains a portfolio-quality
  local and CI artifact.

## Acceptance evidence

- reset responses do not reveal account eligibility;
- raw reset token material is absent from durable records and task payloads;
- reset confirmation invalidates all active refresh sessions for the user;
- a verified replay of a revoked refresh token invalidates remaining sessions
  in that token family;
- session APIs enforce authenticated ownership;
- migrations and reviewed public contract match runtime behavior.
