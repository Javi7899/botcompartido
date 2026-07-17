from pathlib import Path

from loguru import logger

from quantbot.config import AppConfig
from quantbot.logging_setup import setup_logging


def test_setup_creates_log_dir_and_writes(tmp_path: Path) -> None:
    config = AppConfig(_env_file=None, log_dir=tmp_path / "logs", log_level="DEBUG")
    setup_logging(config)
    logger.info("mensaje de prueba")
    logger.complete()

    log_files = list((tmp_path / "logs").glob("quantbot_*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "mensaje de prueba" in content


def test_log_level_filters_below_threshold(tmp_path: Path) -> None:
    config = AppConfig(_env_file=None, log_dir=tmp_path / "logs", log_level="WARNING")
    setup_logging(config)
    logger.info("no debe aparecer")
    logger.warning("si debe aparecer")
    logger.complete()

    content = next((tmp_path / "logs").glob("quantbot_*.log")).read_text(encoding="utf-8")
    assert "no debe aparecer" not in content
    assert "si debe aparecer" in content
