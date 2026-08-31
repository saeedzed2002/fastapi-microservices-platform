# Phase 14 Plan — Catalog product reviews and moderation

## Outcome

Provide a bounded, moderated product-review capability that demonstrates clear
Catalog ownership, public privacy boundaries, authenticated write controls, and
administrator moderation without inventing a cross-service profile dependency.

## Scope

- Catalog-owned review records and migration;
- customer text review submissions for published products;
- one direct reply level, including official administrator replies;
- `pending`, `approved`, and `rejected` moderation lifecycle;
- cursor-paginated public approved tree and administrator moderation queue;
- public API contract, ADR, runbook, service documentation, and unit tests.

## Non-goals

- verified-purchase claims or Order database access;
- star ratings, votes, attachments, edits, deletion, reports, notifications, or
  arbitrary nesting;
- public user IDs, profile fields, or a synchronous Customer/Identity profile
  lookup;
- review events or search indexing. Reviews do not yet drive another service.

## Acceptance evidence

- public reads contain only approved records and no author identifiers;
- a non-approved root cannot receive a reply;
- a reply cannot be approved if its root is hidden;
- `admin` moderation is explicit and auditable;
- public and moderation pagination use opaque cursors;
- migration, reviewed contract, lint, and tests agree with runtime behavior.
