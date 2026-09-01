# Catalog Service

Catalog owns products, variants, categories, brands, prices, attributes, and product lifecycle.

It also owns product-review text, one-level replies, and moderation state. It
stores the authenticated author subject only as an opaque identifier for the
administrator queue; public review responses contain generic labels and never
call Identity or Customer for profile data.

It stores only opaque media asset identifiers. It never queries the Media Service database or stores file bytes. Published product responses contain ordered, same-origin Media redirect paths in `media_urls`; clients must not treat the opaque `media_asset_ids` as URLs.

## API

- GET /api/v1/catalog/products with `limit` and an opaque `cursor`, returning `items` and `next_cursor`
- GET /api/v1/catalog/products/{slug}
- GET /api/v1/catalog/products/{slug}/reviews with `limit` and an opaque `cursor`
- POST /api/v1/catalog/products/{product_id}/reviews for authenticated submissions
- POST /api/v1/catalog/reviews/{review_id}/replies for one direct reply
- GET /api/v1/catalog/admin/reviews and POST /api/v1/catalog/admin/reviews/{review_id}/moderation for administrators
- GET /api/v1/catalog/categories and GET /api/v1/catalog/categories/{slug}
- GET /api/v1/catalog/brands and GET /api/v1/catalog/brands/{slug}
- GET /api/v1/catalog/admin/products with optional `status=draft|published|archived`, and GET /api/v1/catalog/admin/products/{product_id}
- `POST`, `PATCH`, and `DELETE` under `/api/v1/catalog/products`; `DELETE` archives, while `/restore` returns an archived product to draft
- `POST`, `PATCH`, and `DELETE` under `/api/v1/catalog/categories` and `/api/v1/catalog/brands`
- `POST`, `PATCH`, and `DELETE` under `/api/v1/catalog/products/{product_id}/media`; delete detaches the media relation and patch changes `sort_order`
- Public active variants at GET /api/v1/catalog/products/{product_id}/variants; administrator create/read/update/retire operations under `/api/v1/catalog/products/{product_id}/variants` and `/api/v1/catalog/admin/products/{product_id}/variants`
- POST /api/v1/catalog/checkout/variants for the authenticated checkout
  snapshot used by Order

Every administrator endpoint and every Catalog mutation requires an access token with `admin`; a customer token receives `403`. Public product and variant reads expose only published products and active variants.
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
never reads Media's database or object storage. Media checks Catalog's separate
signed reference-status endpoint before deleting a product-image asset. Catalog
product lifecycle changes publish the versioned facts consumed by Search
through its local transactional outbox. See
[`docs/architecture/catalog-management.md`](../../docs/architecture/catalog-management.md)
for the complete authority and API semantics.
