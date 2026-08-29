# Local Zarinpal sandbox checkout

This runbook exercises a customer-owned checkout through the local edge. It
does not bypass authentication, create JWTs by hand, expose internal endpoints,
or write directly to a service database.

## Prerequisites

1. Copy `.env.example` to the ignored `.env` file. Set a unique value of at
   least 32 characters for `PLATFORM_INTERNAL_OTP_SHARED_SECRET`.
2. Configure a working SMS.ir API key and line number so the customer can
   receive an OTP:

       NOTIFICATION_SMSIR_ENABLED=true
       NOTIFICATION_SMSIR_API_KEY=<your-smsir-api-key>
       NOTIFICATION_SMSIR_LINE_NUMBER=<your-smsir-line-number>

3. Configure a sandbox merchant ID. Keep the callback on the local edge when
   the browser and Docker Compose run on the same machine:

       ZARINPAL_MERCHANT_ID=<your-zarinpal-sandbox-merchant-id>
       ZARINPAL_SANDBOX=true
       ZARINPAL_CALLBACK_URL=https://localhost/api/v1/payments/zarinpal/callback

4. Generate and trust the local edge certificate in the browser that will
   complete payment, then start the platform and migrate every service:

       pwsh -NoProfile -File .\scripts\new_local_edge_certificate.ps1
       pwsh -NoProfile -File .\scripts\platform.ps1 -Task dev-up
       pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-identity
       pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-customer
       pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-catalog
       pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-inventory
       pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-order
       pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-payment
       pwsh -NoProfile -File .\scripts\platform.ps1 -Task migrate-notification

The supplied local callback works only when the browser returns on the same
machine. A remotely used sandbox environment needs a deployed public `HTTPS`
edge URL registered with Zarinpal.

## Create the administrator and catalog data

Provision the initial administrator interactively. The password is prompted
for and must never be placed on a command line:

    pwsh -NoProfile -File .\scripts\platform.ps1 -Task provision-admin -AdminEmail admin@example.com

In PowerShell 7, sign in and retain the administrator token only in the current
shell. `-SkipCertificateCheck` is local-only and must not be used against a
deployed environment:

```powershell
$baseUrl = "https://localhost"
$admin = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body (@{ email = "admin@example.com"; password = "<administrator-password>" } | ConvertTo-Json)
$adminHeaders = @{ Authorization = "Bearer $($admin.access_token)" }
```

Category rows exist in the Catalog database, but this repository does not yet
expose a category-management API. Do not insert a category directly into the
database. `category_id` is optional, so omit it for this checkout test.

Create, publish, and stock an `IRT` product:

```powershell
$suffix = [guid]::NewGuid().ToString("N").Substring(0, 12)
$sku = "ZAR-$suffix".ToUpperInvariant()
$product = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/catalog/products" -Headers $adminHeaders `
  -ContentType "application/json" `
  -Body (@{
    name = "Zarinpal sandbox $suffix"
    slug = "zarinpal-sandbox-$suffix"
    description = "Local sandbox checkout product"
    price_amount = "150000"
    currency = "IRT"
    attributes = @{}
  } | ConvertTo-Json)

$variant = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/catalog/products/$($product.id)/variants" -Headers $adminHeaders `
  -ContentType "application/json" `
  -Body (@{ sku = $sku; name = "Default"; attributes = @{} } | ConvertTo-Json)

Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/catalog/products/$($product.id)/publish" -Headers $adminHeaders

Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/inventory/stock-items" -Headers $adminHeaders `
  -ContentType "application/json" `
  -Body (@{ sku = $sku; initial_quantity = 2 } | ConvertTo-Json)
```

## Create and authenticate the customer

Customer registration is OTP-only. The first successful verification creates
the Identity account. Request an OTP, read it from the configured SMS.ir
destination, and verify it:

```powershell
$phone = "09121234567"
Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/auth/otp/request" `
  -ContentType "application/json" `
  -Body (@{ phone = $phone } | ConvertTo-Json)

$customer = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/auth/otp/verify" `
  -ContentType "application/json" `
  -Body (@{ phone = $phone; code = "<six-digit-code-from-sms>" } | ConvertTo-Json)
$customerHeaders = @{ Authorization = "Bearer $($customer.access_token)" }
```

Set a contact email and delivery address. Checkout rejects a customer without
a contact email:

```powershell
Invoke-RestMethod -SkipCertificateCheck -Method Put `
  -Uri "$baseUrl/api/v1/customers/me" -Headers $customerHeaders `
  -ContentType "application/json" `
  -Body (@{
    display_name = "Sandbox Customer"
    email = "customer@example.com"
    phone = $phone
  } | ConvertTo-Json)

$address = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/customers/me/addresses" -Headers $customerHeaders `
  -ContentType "application/json" `
  -Body (@{
    label = "Home"
    recipient_name = "Sandbox Customer"
    line1 = "1 Test Street"
    city = "Tehran"
    postal_code = "1000000000"
    country_code = "IR"
    is_default = $true
  } | ConvertTo-Json)
```

## Checkout and verify payment

Create an order with `zarinpal`, then wait until Kafka has moved it to
`PAYMENT_PENDING` before starting the browser redirect:

```powershell
$order = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/orders" -Headers (@{
    Authorization = $customerHeaders.Authorization
    "Idempotency-Key" = "zarinpal-$suffix"
  }) `
  -ContentType "application/json" `
  -Body (@{
    address_id = $address.id
    items = @(@{ variant_id = $variant.id; quantity = 1 })
    payment_method = "zarinpal"
  } | ConvertTo-Json -Depth 4)

for ($attempt = 0; $attempt -lt 90; $attempt++) {
  $currentOrder = Invoke-RestMethod -SkipCertificateCheck `
    -Uri "$baseUrl/api/v1/orders/$($order.id)" -Headers $customerHeaders
  if ($currentOrder.status -eq "PAYMENT_PENDING") {
    break
  }
  Start-Sleep -Milliseconds 500
}
if ($currentOrder.status -ne "PAYMENT_PENDING") {
  throw "order did not reach PAYMENT_PENDING within 45 seconds"
}

$payment = Invoke-RestMethod -SkipCertificateCheck -Method Post `
  -Uri "$baseUrl/api/v1/payments/orders/$($order.id)/zarinpal" -Headers $customerHeaders
Start-Process $payment.redirect_url
```

Complete the sandbox payment in the browser. The browser returns to the local
edge callback, which verifies the authority server-to-server. Confirm that the
order becomes `CONFIRMED`:

```powershell
Invoke-RestMethod -SkipCertificateCheck `
  -Uri "$baseUrl/api/v1/orders/$($order.id)" -Headers $customerHeaders
```

Expected states are `PAYMENT_PENDING` before the redirect and `CONFIRMED` after
verified return. If the order remains pending, inspect the Payment and Kafka
outbox logs first. Do not retry a `REQUESTING` payment automatically; follow
the [Zarinpal recovery runbook](zarinpal-payment.md).
