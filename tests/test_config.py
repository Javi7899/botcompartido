from pathlib import Path

import pytest
from pydantic import ValidationError

from quantbot.config import MARKET_TIMEZONE, AppConfig


def test_defaults() -> None:
    config = AppConfig(_env_file=None)
    assert config.environment == "dev"
    assert config.log_level == "INFO"
    assert config.db_path == Path("data") / "quantbot.sqlite"
    assert config.log_dir == Path("logs")


def test_market_timezone_is_new_york() -> None:
    assert MARKET_TIMEZONE == "America/New_York"


def test_sec_user_agent_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    default = AppConfig(_env_file=None)
    assert "@" in default.sec_user_agent  # formato con email de contacto
    monkeypatch.setenv("QUANTBOT_SEC_USER_AGENT", "acme research a@b.com")
    assert AppConfig(_env_file=None).sec_user_agent == "acme research a@b.com"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTBOT_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("QUANTBOT_ENVIRONMENT", "paper")
    config = AppConfig(_env_file=None)
    assert config.log_level == "DEBUG"
    assert config.environment == "paper"


def test_invalid_log_level_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTBOT_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValidationError):
        AppConfig(_env_file=None)


def test_invalid_environment_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTBOT_ENVIRONMENT", "production")
    with pytest.raises(ValidationError):
        AppConfig(_env_file=None)


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig(_env_file=None, typo_field=True)  # type: ignore[call-arg]
