from pathlib import Path

SERVICES = (
    "reference-service",
    "identity-service",
    "customer-service",
    "catalog-service",
    "search-service",
    "media-service",
    "inventory-service",
    "cart-service",
    "order-service",
    "payment-service",
    "notification-service",
    "chat-service",
)


def test_ghcr_publication_uses_one_job_and_scans_every_exact_image() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "platform-ci.yml"
    ).read_text(encoding="utf-8")

    publish_job = workflow.split("  publish-ghcr:\n", maxsplit=1)[1]

    assert "matrix:" not in publish_job
    assert "name: Publish scanned service images to GHCR" in publish_job
    assert "packages: write" in publish_job
    assert "Build all immutable service images" in publish_job
    assert "Publish all scanned immutable service images" in publish_job

    authentication_marker = "Authenticate to GitHub Container Registry after every scan gate"
    for service in SERVICES:
        scan_marker = f"Scan {service} image for high and critical vulnerabilities"
        assert f"local/{service}:${{{{ github.sha }}}}" in publish_job
        assert scan_marker in publish_job
        assert publish_job.index(scan_marker) < publish_job.index(authentication_marker)

    assert "severity: HIGH,CRITICAL" in publish_job
    assert 'exit-code: "1"' in publish_job
    assert 'docker push "${image}:sha-${revision}"' in publish_job
