from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_platform_script_uses_root_compose_configuration() -> None:
    script = (REPOSITORY_ROOT / "scripts" / "platform.ps1").read_text(encoding="utf-8")

    assert "$composeArguments = @()" in script
    assert "& docker compose @composeArguments up -d" in script
    assert '"dev-start" { & docker compose @composeArguments start }' in script
    assert '"dev-stop" { & docker compose @composeArguments stop }' in script
    assert '"dev-recreate" { & docker compose @composeArguments up -d --force-recreate }' in script


def test_sms_otp_runbook_uses_root_compose_environment() -> None:
    runbook = (REPOSITORY_ROOT / "docs" / "runbooks" / "sms-otp.md").read_text(encoding="utf-8")

    assert "docker compose up -d --build" in runbook
    assert "The root `.env` sets `COMPOSE_FILE`" in runbook


def test_root_environment_selects_the_canonical_compose_file() -> None:
    environment_example = (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "COMPOSE_FILE=infrastructure/compose/docker-compose.yml" in environment_example
