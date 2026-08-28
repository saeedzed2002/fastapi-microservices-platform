from identity_service.admin_provision import parse_arguments


def test_admin_provision_requires_an_explicit_email() -> None:
    parsed = parse_arguments(["--email", "ADMIN@example.com"])

    assert parsed.email == "ADMIN@example.com"
