"""Application configuration (pydantic-settings).

Config values can be overridden via environment variables with the
``QUANTBOT_`` prefix (e.g. ``QUANTBOT_LOG_LEVEL=DEBUG``) or a local ``.env``
file (gitignored). Unknown keys are rejected (``extra="forbid"``) so typos
fail loudly instead of being silently ignored.
"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# IANA timezone of the market the bot trades on (spec section 1.1: all market
# clock logic must go through zoneinfo with this key — never a fixed offset).
MARKET_TIMEZONE = "America/New_York"

LogLevel = Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QUANTBOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # dev: local development. paper: IBKR paper trading (Fase 8).
    # live: real capital (Fase 9, requires explicit user approval).
    environment: Literal["dev", "paper", "live"] = "dev"

    db_path: Path = Path("data") / "quantbot.sqlite"
    log_dir: Path = Path("logs")
    log_level: LogLevel = "INFO"

    # La SEC exige un User-Agent con un contacto real (formato
    # "nombre contacto email"); rechaza con HTTP 403 los genéricos.
    # Se configura vía QUANTBOT_SEC_USER_AGENT para no fijar un email en el
    # repo. El default es un placeholder que la SEC rechazará hasta que se
    # ponga un contacto real (fallo ruidoso, no silencioso).
    sec_user_agent: str = "botcompartido quantbot contacto@example.com"

    # Modelo LLM del supervisor (Capa 2.3). Se persiste con cada decisión;
    # cambiarlo invalida los backtests del supervisor (que no existen: se
    # valida en paper trading, Enmienda 7).
    supervisor_model: str = "claude-opus-4-8"


def load_config() -> AppConfig:
    """Build the config from environment/.env; raises ValidationError on bad values."""
    return AppConfig()
