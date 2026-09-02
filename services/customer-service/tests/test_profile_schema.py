import pytest
from pydantic import ValidationError

from customer_service.schemas import AddressCreate, AddressUpdate, ProfileUpsert


def test_profile_contact_email_is_normalized() -> None:
    profile = ProfileUpsert(display_name="Customer", email="CUSTOMER@Example.com")

    assert profile.email == "customer@example.com"


@pytest.mark.parametrize(
    ("schema", "expected_country_code"),
    (
        (
            AddressCreate(
                label="Home",
                recipient_name="Customer",
                line1="1 Main",
                city="Tehran",
                postal_code="1000000000",
                country_code="ir",
            ),
            "IR",
        ),
        (AddressUpdate(country_code="de"), "DE"),
    ),
)
def test_address_country_codes_are_normalized(
    schema: AddressCreate | AddressUpdate, expected_country_code: str
) -> None:
    assert schema.country_code == expected_country_code


def test_address_country_code_requires_an_iso_sized_value() -> None:
    with pytest.raises(ValidationError):
        AddressCreate(
            label="Home",
            recipient_name="Customer",
            line1="1 Main",
            city="Tehran",
            postal_code="1000000000",
            country_code="IRN",
        )
