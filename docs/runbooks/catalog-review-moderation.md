# Catalog review moderation

## Scope

Catalog owns product-review records and moderation state. Customers submit text
for a published product; those records normally begin as `pending`. Public
reads show only approved roots and approved direct replies. This runbook does
not make a verified-purchase claim and does not fetch Customer or Identity
profile data.

## List pending submissions

Use an administrator access token. The administrator response includes the
opaque author ID for investigation, but never copy it to public content.

```powershell
$baseUrl = "https://localhost"
$headers = @{ Authorization = "Bearer <admin-access-token>" }
Invoke-RestMethod -Uri "$baseUrl/api/v1/catalog/admin/reviews?status=pending" -Headers $headers
```

Use the opaque `next_cursor` from the response without decoding or editing it.
Filter a product when investigating a specific listing with
`?status=pending&product_id=<product-uuid>`.

## Approve or reject

Review the text and its parent state before approving. A reply whose root is
pending or rejected cannot be approved. The note is administrator-visible
metadata, not a customer message.

```powershell
Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/api/v1/catalog/admin/reviews/<review-uuid>/moderation" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"status":"approved","moderation_note":"Reviewed for relevance"}'
```

To reject, change `approved` to `rejected`. Rejecting a root makes its replies
unavailable through the public endpoint even if they were previously approved.

## Failure behavior

- Invalid text is rejected with `422` before any write.
- A customer cannot submit to a draft or missing product; the response is
  `404`.
- A reply to a pending or rejected root is rejected with `409`.
- Catalog stores no public profile attributes. If an operator needs an identity
  investigation, use approved staff tools outside the public review response.
