from search_service.main import app


def test_search_openapi_exposes_only_the_public_query_endpoint() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/search/products" in paths
    assert "/api/v1/search/admin/rebuild" not in paths
