from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dependabot_uses_a_bounded_monthly_version_update_queue() -> None:
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    assert config.count("package-ecosystem:") == 4
    assert config.count("interval: monthly") == 4
    assert config.count("open-pull-requests-limit: 1") == 4
    assert "open-pull-requests-limit: 0" not in config
    assert "open-pull-requests-limit: 5" not in config
    assert "updates remain enabled separately and are not subject to this limit." in config
