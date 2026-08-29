# Catalog category administration

## Purpose

Catalog owns categories and their parent/child hierarchy. Categories are read
publicly; only an authenticated `admin` or `catalog_admin` may create, update,
or delete them.

## Prerequisites

Use a local administrator access token. The local edge certificate is
self-signed, so `-SkipCertificateCheck` is permitted only for `localhost`.

```powershell
$baseUrl = "https://localhost"
$admin = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body (@{ email = "admin@example.com"; password = "<administrator-password>" } | ConvertTo-Json)
$adminHeaders = @{ Authorization = "Bearer $($admin.access_token)" }
```

## Create a root category

```powershell
$category = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/catalog/categories" -Headers $adminHeaders `
  -ContentType "application/json" `
  -Body (@{ name = "Electronics"; slug = "electronics" } | ConvertTo-Json)
```

The `slug` must be lowercase ASCII words separated by single hyphens. Save
`$category.id` when assigning the category to a product.

## Create a child category

```powershell
$childCategory = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/catalog/categories" -Headers $adminHeaders `
  -ContentType "application/json" `
  -Body (@{
    name = "Mobile Phones"
    slug = "mobile-phones"
    parent_id = $category.id
  } | ConvertTo-Json)
```

The API rejects a missing parent, a category assigned to itself, and changes
that would create a parent/child cycle.

## Read, update, and assign

```powershell
Invoke-RestMethod -SkipCertificateCheck `
  -Uri "$baseUrl/api/v1/catalog/categories"

Invoke-RestMethod -SkipCertificateCheck `
  -Uri "$baseUrl/api/v1/catalog/categories/electronics"

$category = Invoke-RestMethod -SkipCertificateCheck -Method Patch `
  -Uri "$baseUrl/api/v1/catalog/categories/$($category.id)" -Headers $adminHeaders `
  -ContentType "application/json" `
  -Body (@{ name = "Consumer Electronics" } | ConvertTo-Json)
```

Use the returned identifier in the product create or update body:

```json
{
  "category_id": "<category-id>"
}
```

Catalog rejects a non-existent `category_id` with `404` instead of allowing a
database foreign-key failure.

## Delete

```powershell
Invoke-RestMethod -SkipCertificateCheck -Method Delete `
  -Uri "$baseUrl/api/v1/catalog/categories/$($childCategory.id)" -Headers $adminHeaders
```

Deletion returns `204` only when the category has no child categories and no
products assigned to it. Reassign products and delete child categories first;
the API returns `409` otherwise.
