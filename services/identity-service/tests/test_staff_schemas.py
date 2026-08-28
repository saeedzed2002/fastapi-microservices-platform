from identity_service.schemas import SupportAgentCreate, SupportAgentStatusUpdate


def test_support_agent_request_normalizes_email_and_limits_statuses() -> None:
    agent = SupportAgentCreate(email="AGENT@Example.com", password="correct horse battery staple")

    assert agent.email == "agent@example.com"
    assert SupportAgentStatusUpdate(status="suspended").status == "suspended"
