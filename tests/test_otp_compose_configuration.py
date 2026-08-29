from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_platform_script_uses_root_env_file_when_present() -> None:
    script = (REPOSITORY_ROOT / "scripts" / "platform.ps1").read_text(encoding="utf-8")

    assert '$composeEnvironmentFile = Join-Path $repoRoot ".env"' in script
    assert '"--env-file", $composeEnvironmentFile' in script
    assert "& docker compose @composeArguments up -d" in script
    assert '"dev-start" { & docker compose @composeArguments start }' in script
    assert '"dev-stop" { & docker compose @composeArguments stop }' in script
    assert '"dev-recreate" { & docker compose @composeArguments up -d --force-recreate }' in script


def test_sms_otp_runbook_uses_the_root_env_wrapper() -> None:
    runbook = (REPOSITORY_ROOT / "docs" / "runbooks" / "sms-otp.md").read_text(encoding="utf-8")

    assert "pwsh -NoProfile -File scripts/platform.ps1 -Task dev-up" in runbook
    assert "`platform.ps1` passes the absolute root `.env` path to Compose." in runbook
