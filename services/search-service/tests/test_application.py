from search_service.application import decode_cursor, encode_cursor


def test_search_cursor_round_trip() -> None:
    assert decode_cursor(encode_cursor(42)) == 42


def test_invalid_search_cursor_is_rejected() -> None:
    try:
        decode_cursor("not-a-cursor")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
    else:
        raise AssertionError("invalid cursor was accepted")
