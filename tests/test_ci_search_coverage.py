from pathlib import Path


def test_search_service_is_covered_by_every_ci_delivery_stage() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "platform-ci.yml"
    ).read_text(encoding="utf-8")

    assert (
        "for service in identity-service customer-service catalog-service search-service"
        in workflow
    )
    assert "          - search-service" in workflow
    assert "services/search-service/alembic.ini upgrade head" in workflow
    assert "tests/e2e/test_phase8_search.py" in workflow
    assert (
        "reference-service identity-service customer-service catalog-service search-service"
        in workflow
    )
