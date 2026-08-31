from pathlib import Path


def test_portfolio_ci_has_no_automatic_registry_delivery() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "platform-ci.yml"
    ).read_text(encoding="utf-8")

    assert "  publish-ghcr:" not in workflow
    assert "packages: write" not in workflow
    assert "docker login ghcr.io" not in workflow
    assert "docker push" not in workflow
    assert "  kubernetes-conformance:" in workflow
    assert "  image-build:" in workflow
    assert "Scan image for high and critical vulnerabilities" in workflow
