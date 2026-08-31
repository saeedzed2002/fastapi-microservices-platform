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


def test_ghcr_publication_scans_the_exact_local_image_before_registry_push() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "platform-ci.yml"
    ).read_text(encoding="utf-8")
    publish_job = workflow.split("  publish-ghcr:\n", maxsplit=1)[1]

    assert "matrix:\n        service:" in publish_job
    for service in SERVICES:
        assert f"          - {service}" in publish_job

    local_image = "local/${{ matrix.service }}:${{ github.sha }}"
    scan_marker = "Scan exact publish image for high and critical vulnerabilities"
    authentication_marker = "Authenticate to GitHub Container Registry after the scan gate"
    publish_marker = "Publish the scanned immutable service image"

    assert local_image in publish_job
    assert publish_job.index(scan_marker) < publish_job.index(authentication_marker)
    assert publish_job.index(authentication_marker) < publish_job.index(publish_marker)
    assert publish_job.index(scan_marker) < publish_job.index(
        'docker push "${image}:sha-${revision}"'
    )
    assert 'docker tag "${LOCAL_IMAGE}" "${image}:sha-${revision}"' in publish_job
    assert "severity: HIGH,CRITICAL" in publish_job
    assert 'exit-code: "1"' in publish_job
