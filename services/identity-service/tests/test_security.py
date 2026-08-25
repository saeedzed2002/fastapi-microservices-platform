from identity_service.security import hash_password, token_hash, verify_password


def test_argon2id_hash_verifies_and_does_not_expose_password() -> None:
    password = "correct horse battery staple"
    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2id$")
    assert verify_password(password, password_hash)
    assert not verify_password("wrong password", password_hash)
    assert password not in password_hash


def test_refresh_token_hash_is_deterministic() -> None:
    assert token_hash("refresh-token") == token_hash("refresh-token")
    assert token_hash("refresh-token") != token_hash("other-token")
