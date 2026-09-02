import asyncio
from uuid import UUID, uuid4

from customer_service.application import provision_customer, provision_identity_customer
from customer_service.models import Customer, InboxMessage


class FakeCustomerSession:
    def __init__(
        self, *, customer: Customer | None, duplicate_event_id: UUID | None = None
    ) -> None:
        self.customer = customer
        self.duplicate_event_id = duplicate_event_id
        self.added: list[object] = []
        self.get_calls = 0

    async def get(self, model: type[Customer], user_id: UUID) -> Customer | None:
        assert model is Customer
        self.get_calls += 1
        assert self.customer is None or self.customer.id == user_id
        return self.customer

    async def scalar(self, _: object) -> UUID | None:
        return self.duplicate_event_id

    def add(self, value: object) -> None:
        self.added.append(value)


def test_customer_provision_uses_email_local_part_then_phone_fallback() -> None:
    async def exercise() -> None:
        email_customer_session = FakeCustomerSession(customer=None)
        email_customer = await provision_customer(
            email_customer_session,
            user_id=uuid4(),
            email="customer@example.com",
        )
        phone_customer_session = FakeCustomerSession(customer=None)
        phone_customer = await provision_customer(
            phone_customer_session,
            user_id=uuid4(),
            email=None,
            phone="989121234567",
        )

        assert email_customer.display_name == "customer"
        assert phone_customer.display_name == "989121234567"
        assert email_customer_session.added == [email_customer]
        assert phone_customer_session.added == [phone_customer]

    asyncio.run(exercise())


def test_existing_customer_projection_updates_contact_without_creating_a_second_customer() -> None:
    async def exercise() -> None:
        customer = Customer(
            id=uuid4(),
            email="old@example.com",
            phone="989100000000",
            display_name="existing",
        )
        session = FakeCustomerSession(customer=customer)

        updated = await provision_customer(
            session,
            user_id=customer.id,
            email="new@example.com",
            phone="989199999999",
        )

        assert updated is customer
        assert customer.email == "new@example.com"
        assert customer.phone == "989199999999"
        assert session.added == []

    asyncio.run(exercise())


def test_identity_projection_records_inbox_and_customer_in_one_session() -> None:
    async def exercise() -> None:
        session = FakeCustomerSession(customer=None)
        user_id = uuid4()
        event_id = uuid4()

        customer = await provision_identity_customer(
            session,
            event_id=event_id,
            event_type="identity.user_registered.v2",
            user_id=user_id,
            email="customer@example.com",
            phone=None,
        )

        assert customer is not None
        assert customer.id == user_id
        assert [type(value) for value in session.added] == [Customer, InboxMessage]
        inbox = session.added[1]
        assert isinstance(inbox, InboxMessage)
        assert inbox.event_id == event_id
        assert inbox.event_type == "identity.user_registered.v2"

    asyncio.run(exercise())


def test_duplicate_identity_event_has_no_customer_side_effect() -> None:
    async def exercise() -> None:
        session = FakeCustomerSession(customer=None, duplicate_event_id=uuid4())

        result = await provision_identity_customer(
            session,
            event_id=uuid4(),
            event_type="identity.user_registered.v1",
            user_id=uuid4(),
            email=None,
            phone="989121234567",
        )

        assert result is None
        assert session.get_calls == 0
        assert session.added == []

    asyncio.run(exercise())
