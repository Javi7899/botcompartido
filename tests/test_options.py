import pandas as pd
import pytest

from quantbot.data.errors import DataSourceError
from quantbot.data.options import assess_option_chain


def chain_frame(
    strikes: list[float], oi: list[int], iv: list[float]
) -> pd.DataFrame:
    return pd.DataFrame(
        {"strike": strikes, "openInterest": oi, "impliedVolatility": iv}
    )


def healthy_chains() -> dict:
    calls = chain_frame([90, 100, 110], [2000, 3000, 1500], [0.25, 0.22, 0.28])
    puts = chain_frame([90, 100, 110], [1800, 2500, 900], [0.30, 0.24, 0.21])
    return {exp: (calls, puts) for exp in ("2026-07-24", "2026-07-31", "2026-08-21")}


def test_healthy_chain_passes() -> None:
    quality = assess_option_chain("AAPL", 100.0, healthy_chains())
    assert quality.passed
    assert quality.total_call_oi == 6500 * 3
    assert quality.strikes_bracket_spot
    assert "OK" in quality.summary()


def test_too_few_expirations_fails() -> None:
    chains = dict(list(healthy_chains().items())[:1])
    quality = assess_option_chain("AAPL", 100.0, chains)
    assert not quality.passed
    assert any("vencimientos" in i for i in quality.issues)


def test_low_oi_fails() -> None:
    calls = chain_frame([90, 100, 110], [10, 20, 5], [0.25, 0.22, 0.28])
    puts = chain_frame([90, 100, 110], [8, 15, 3], [0.30, 0.24, 0.21])
    chains = {e: (calls, puts) for e in ("2026-07-24", "2026-07-31", "2026-08-21")}
    quality = assess_option_chain("AAPL", 100.0, chains)
    assert any("open interest" in i for i in quality.issues)


def test_missing_iv_fails() -> None:
    calls = chain_frame([90, 100, 110], [2000, 3000, 1500], [0.0, None, 0.28])
    puts = chain_frame([90, 100, 110], [1800, 2500, 900], [None, 0.0, 0.21])
    chains = {e: (calls, puts) for e in ("2026-07-24", "2026-07-31", "2026-08-21")}
    quality = assess_option_chain("AAPL", 100.0, chains)
    assert any("IV ausente" in i for i in quality.issues)


def test_strikes_not_bracketing_spot_fails() -> None:
    quality = assess_option_chain("AAPL", 500.0, healthy_chains())
    assert any("no rodean el spot" in i for i in quality.issues)


def test_missing_column_raises() -> None:
    bad = pd.DataFrame({"strike": [100], "openInterest": [50]})
    with pytest.raises(DataSourceError, match="impliedVolatility"):
        assess_option_chain("AAPL", 100.0, {"2026-07-24": (bad, bad)})


def test_no_chains_raises() -> None:
    with pytest.raises(DataSourceError, match="ninguna cadena"):
        assess_option_chain("AAPL", 100.0, {})
