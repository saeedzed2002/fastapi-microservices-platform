# Catalog management and storefront-read contract

## Authority model

Catalog is the canonical owner of products, variants, categories, brands, and
product/media relationships. Media owns asset bytes, processing, and deletion
state. An access token with `admin` is required for every write described
below. A `customer` token never receives a management capability merely by
being authenticated.

| Resource | Customer/public access | Administrator access | Delete semantics |
|---|---|---|---|
| Product | Published list and read | Create, update, publish, archive, restore, admin list/read | Archive; restore returns it to `draft` |
| Variant | Active variants of a published product | Create, read all, update, retire | Retire (`is_active=false`) |
| Category | List and read by slug | Create, update, delete | Reject if it has a child or assigned product |
| Brand | List and read by slug | Create, update, delete | Reject if assigned to a product |
| Product-media relation | Media URLs in published product response | Attach, reorder, detach | Delete only the Catalog relation |
| Media asset | Public redirect only for ready product-image thumbnail | Upload, list, inspect, delete owned asset | Reject deletion while Catalog references a product image |

## Catalog HTTP API

All write routes below require `Authorization: Bearer <admin-access-token>`.
Only the `/admin/` reads require a token; storefront reads are deliberately
anonymous and expose published/active data only.

| Operation | Route | Request body / result |
|---|---|---|
| Storefront products | `GET /api/v1/catalog/products` | `limit`, opaque `cursor`; published product page |
| Storefront product | `GET /api/v1/catalog/products/{slug}` | Published product only |
| Admin product page | `GET /api/v1/catalog/admin/products` | Optional `status=draft|published|archived`, `limit`, opaque `cursor` |
| Admin product | `GET /api/v1/catalog/admin/products/{product_id}` | Includes draft and archived products |
| Create product | `POST /api/v1/catalog/products` | `name`, `slug`, optional `description`, `brand_id`, `category_id`, positive `price_amount`, three-letter `currency`, string `attributes` |
| Update product | `PATCH /api/v1/catalog/products/{product_id}` | Any mutable create field; `slug`, brand and category are validated |
| Archive / restore / publish | `DELETE /api/v1/catalog/products/{product_id}`; `POST /{product_id}/restore`; `POST /{product_id}/publish` | Archive is idempotent; restore is allowed only from archived and produces draft |
| Categories | `GET /api/v1/catalog/categories`; `GET /categories/{slug}`; `POST`, `PATCH`, `DELETE /categories/{category_id}` | `name`, URL-safe `slug`, optional `parent_id`; hierarchy cycles are rejected |
| Brands | `GET /api/v1/catalog/brands`; `GET /brands/{slug}`; `POST`, `PATCH`, `DELETE /brands/{brand_id}` | `name`, URL-safe unique `slug` |
| Public variants | `GET /api/v1/catalog/products/{product_id}/variants` | Only active variants; draft/archived parent returns `404` |
| Admin variants | `GET /api/v1/catalog/admin/products/{product_id}/variants`; `POST /products/{product_id}/variants`; `PATCH`, `DELETE /products/{product_id}/variants/{variant_id}` | Create requires immutable `sku`, `name`, optional price and attributes; patch can modify `name`, `price_amount`, `attributes`, `is_active`; delete retires |
| Product media | `POST /api/v1/catalog/products/{product_id}/media`; `PATCH`, `DELETE /products/{product_id}/media/{media_asset_id}` | Attach `{media_asset_id, sort_order}`; patch `{sort_order}`; delete detaches the relation |

`ProductResponse.media_urls` is ordered identically to `media_asset_ids` and
contains same-origin paths such as
`/api/v1/media/public/product-images/{asset_id}`. A client must not construct
object-store URLs or treat `media_asset_ids` as public URLs.

## Media flow for product images

1. An administrator requests `POST /api/v1/media/uploads` with
   `purpose=product_image`.
2. The browser uploads with the returned presigned URL and completes the asset.
3. Once Media has processed the image to `ready`, the same administrator
   attaches its opaque `asset_id` to a product through Catalog.
4. The storefront uses Catalog's `media_urls`; Media checks that the asset is a
   ready, non-deleted product-image thumbnail and redirects to a short-lived
   object-store URL.
5. To remove an image from a product, detach it in Catalog. To reclaim the
   detached asset, the owning administrator calls
   `DELETE /api/v1/media/assets/{asset_id}`. Media checks Catalog's signed
   internal reference-status route and returns `409` if any product still
   references it.

`GET /api/v1/media/assets` and `GET /api/v1/media/assets/{asset_id}` are owner
scoped. `DELETE /api/v1/media/assets/{asset_id}` starts durable asynchronous
cleanup and returns `202`; its final lifecycle state is `deleted`, not an
immediate byte-removal guarantee.
