# Catalog Service

Catalog owns products, variants, categories, brands, prices, attributes, and product lifecycle.

It also owns product-review text, one-level replies, and moderation state. It
stores the authenticated author subject only as an opaque identifier for the
administrator queue; public review responses contain generic labels and never
call Identity or Customer for profile data.

It stores only opaque media asset identifiers. It never queries the Media Service database or stores file bytes. The initial Phase 3 API exposes those references; a future edge/read projection will resolve publicly publishable media after an explicit contract is approved.

## API

- GET /api/v1/catalog/products with `limit` and an opaque `cursor`, returning `items` and `next_cursor`
- GET /api/v1/catalog/products/{slug}
- GET /api/v1/catalog/products/{slug}/reviews with `limit` and an opaque `cursor`
- POST /api/v1/catalog/products/{product_id}/reviews for authenticated submissions
- POST /api/v1/catalog/reviews/{review_id}/replies for one direct reply
- GET /api/v1/catalog/admin/reviews and POST /api/v1/catalog/admin/reviews/{review_id}/moderation for administrators
- GET /api/v1/catalog/categories
- GET /api/v1/catalog/categories/{slug}
- `POST`, `PATCH`, and `DELETE` under `/api/v1/catalog/products`, plus
  `/publish`, `/media`, and `/variants`
- `POST`, `PATCH`, and `DELETE` under `/api/v1/catalog/categories`
- POST /api/v1/catalog/checkout/variants for the authenticated checkout
  snapshot used by Order

The administrator endpoints require an access token with `admin`.
Category writes validate the parent hierarchy and reject deleting a category that
still has child categories or assigned products.

## Operations and verification

`GET /health/live`, `GET /health/ready`, and `GET /metrics` are the service
operational endpoints. Apply the local schema with
`pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-catalog` and run
focused checks with
`uv run --package catalog-service pytest services/catalog-service/tests -q`.

Product media attachment is an administrator operation. Catalog validates the
opaque asset reference through Media's authenticated internal contract; it
never reads Media's database or object storage. Catalog product lifecycle
changes publish the versioned facts consumed by Search through its local
transactional outbox.
