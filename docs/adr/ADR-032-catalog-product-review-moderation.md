# ADR-032 — Catalog product reviews, replies, and moderation

- Status: `Accepted`
- Date: `2026-08-31`
- Owners: platform architecture
- Supersedes: none
- Superseded by: none

## Context

Published Catalog products lacked a customer-feedback workflow. Adding comments
must not let Catalog query Identity or Customer databases for profile data, and
unbounded reply trees or automatic publication create avoidable moderation and
query risks.

## Decision

Catalog owns durable product-review records. Each record contains the product
reference, opaque authenticated subject ID, caller role label, body, moderation
state, optional parent review, and moderation audit metadata. The subject ID is
not a cross-service foreign key and never appears in public review responses.

Customers submit root reviews and replies in `pending` state. `admin` callers
may submit an official reply in `approved` state. An administrator explicitly
approves or rejects every other submission. Public product reads return only
approved root reviews and approved direct replies. They expose the generic
labels `Customer` and `Store team`, never profile attributes, user IDs, or
moderation state.

Replies are limited to one level and require an approved root review. This
makes pagination and public reads bounded to two Catalog queries: a page of
roots plus their direct replies. A reply cannot be approved while its root
review is hidden. Review creation is allowed only for a published product.

The first version does not claim verified-purchase status, add star ratings,
support edits/deletes, or publish a review event. Purchase verification needs a
separate approved Order-owned contract; ratings and lifecycle changes need their
own product policy.

## Consequences

- Catalog gains a complete moderated text-feedback baseline without sharing
  profile/domain models or adding a synchronous dependency on another service.
- Customers can receive a successful submission that remains invisible until
  moderated. The response explicitly reports `pending` or `approved`.
- Administrators receive author IDs only through the administrator moderation
  API, where they are needed for abuse investigation.
- Root review rejection automatically hides any previously approved reply from
  the public tree, even though the reply record remains auditable.

## Alternatives considered

- Store display names by querying Customer during public reads: rejected because
  it introduces a remote dependency and creates a profile-data ownership leak.
- Put reviews in Chat: rejected because feedback is Catalog product state, not
  a customer-support conversation.
- Allow arbitrary nested replies: rejected because it complicates ordering,
  moderation inheritance, and bounded query behavior with no current product
  requirement.
- Auto-approve all customer submissions: rejected because public content needs
  an explicit abuse-control baseline.

## Compatibility and migration

The migration adds an owned `product_reviews` table and indexes for public
pagination, author investigation, and parent lookup. Existing product APIs and
events are unchanged. The reviewed public contract is additive under `/api/v1`.

## Validation

- Unit tests cover trimmed input, pending customer submissions, one-level reply
  enforcement, approval inheritance, cursor round trips, and public privacy
  boundaries.
- Route-schema tests cover public, authenticated, and administrator-only
  endpoint exposure; unit tests exercise the moderation rules.
- Migration SQL renders offline before a database is changed.

## Related material

- [Catalog reviews API contract](../../contracts/openapi/catalog-reviews.v1.openapi.json)
- [Catalog review moderation runbook](../runbooks/catalog-review-moderation.md)
- [Catalog boundary](../architecture/service-boundaries.md)
