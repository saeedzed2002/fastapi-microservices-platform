from media_service.main import app


def test_service_title() -> None:
    assert app.title == "Media Service"
