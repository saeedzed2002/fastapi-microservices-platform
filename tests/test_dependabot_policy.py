from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_routine_dependabot_updates_do_not_create_version_update_branches() -> None:
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert config.count("package-ecosystem:") == 4
    assert config.count("open-pull-requests-limit: 0") == 4
    assert "open-pull-requests-limit: 5" not in config
    assert "Dependabot security updates remain enabled separately." in config
