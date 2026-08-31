from pathlib import Path


def test_no_browser_cors_policy_is_enabled_before_a_frontend_decision() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    service_sources = (repository_root / "services").glob("*/src/**/*.py")
    service_source = "\n".join(path.read_text(encoding="utf-8") for path in service_sources)
    edge_config = (repository_root / "infrastructure" / "edge" / "nginx.conf").read_text(
        encoding="utf-8"
    )

    assert "CORSMiddleware" not in service_source
    assert "access-control-allow-origin" not in edge_config.lower()


def test_browser_token_and_cors_boundary_is_recorded_in_the_accepted_adr() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    adr = (
        repository_root / "docs" / "adr" / "ADR-036-browser-origin-and-token-boundary.md"
    ).read_text(encoding="utf-8")

    for expected_text in (
        "CORS",
        "JSON",
        "HttpOnly",
        "CSRF",
        "local-development credentials",
    ):
        assert expected_text in adr
