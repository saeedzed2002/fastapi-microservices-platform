from customer_service.schemas import ProfileUpsert


def test_profile_contact_email_is_normalized() -> None:
    profile = ProfileUpsert(display_name="Customer", email="CUSTOMER@Example.com")

    assert profile.email == "customer@example.com"
