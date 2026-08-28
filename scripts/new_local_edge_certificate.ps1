[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) "infrastructure/edge/tls"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$certificatePath = Join-Path $OutputDirectory "tls.crt"
$privateKeyPath = Join-Path $OutputDirectory "tls.key"

if ((Test-Path -LiteralPath $certificatePath) -or (Test-Path -LiteralPath $privateKeyPath)) {
    if (-not $Force) {
        throw "A local edge certificate already exists. Use -Force to replace it deliberately."
    }
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$rsa = [System.Security.Cryptography.RSA]::Create(2048)
try {
    $request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
        "CN=localhost",
        $rsa,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
    )
    $subjectAlternativeNames = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
    $subjectAlternativeNames.AddDnsName("localhost")
    $subjectAlternativeNames.AddIPAddress([System.Net.IPAddress]::Loopback)
    $subjectAlternativeNames.AddIPAddress([System.Net.IPAddress]::IPv6Loopback)
    $request.CertificateExtensions.Add($subjectAlternativeNames.Build())
    $request.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $true)
    )
    $request.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
            [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor
                [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment,
            $true
        )
    )
    $request.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509SubjectKeyIdentifierExtension]::new($request.PublicKey, $false)
    )

    $certificate = $request.CreateSelfSigned(
        [System.DateTimeOffset]::UtcNow.AddMinutes(-5),
        [System.DateTimeOffset]::UtcNow.AddDays(30)
    )
    try {
        $utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($certificatePath, $certificate.ExportCertificatePem(), $utf8WithoutBom)
        [System.IO.File]::WriteAllText($privateKeyPath, $rsa.ExportPkcs8PrivateKeyPem(), $utf8WithoutBom)
    }
    finally {
        $certificate.Dispose()
    }
}
finally {
    $rsa.Dispose()
}

Write-Host "Created local self-signed edge certificate at $certificatePath."
