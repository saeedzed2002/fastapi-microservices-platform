from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_platform_script_uses_root_env_file_when_present() -> None:
    script = (REPOSITORY_ROOT / "scripts" / "platform.ps1").read_text(encoding="utf-8")

    assert '$composeEnvironmentFile = Join-Path $repoRoot ".env"' in script
    assert '"--env-file", $composeEnvironmentFile' in script
    assert "& docker compose @composeArguments up -d" in script


def test_sms_otp_runbook_requires_the_root_env_file() -> None:
    runbook = (REPOSITORY_ROOT / "docs" / "runbooks" / "sms-otp.md").read_text(encoding="utf-8")

    assert (
        "docker compose --env-file .env -f infrastructure/compose/docker-compose.yml up -d --build"
    ) in runbook
