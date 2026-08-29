# Catalog Service

Catalog owns products, variants, categories, brands, prices, attributes, and product lifecycle.

It stores only opaque media asset identifiers. It never queries the Media Service database or stores file bytes. The initial Phase 3 API exposes those references; a future edge/read projection will resolve publicly publishable media after an explicit contract is approved.

## API

- GET /api/v1/catalog/products
- GET /api/v1/catalog/products/{slug}
- GET /api/v1/catalog/categories
- GET /api/v1/catalog/categories/{slug}
- Catalog administrator endpoints under /api/v1/catalog/products
- Catalog administrator endpoints under /api/v1/catalog/categories

The administrator endpoints require an access token with `admin` or `catalog_admin`.
Category writes validate the parent hierarchy and reject deleting a category that
still has child categories or assigned products.
