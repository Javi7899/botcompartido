from datetime import date

import pandas as pd
import pytest

from quantbot.data.errors import DataQualityError, DataSourceError
from quantbot.db.models import EngineName
from quantbot.engines.gex import (
    CONTRACT_MULTIPLIER,
    GexEngine,
    black_scholes_gamma,
    compute_gex_profile,
)

AS_OF = date(2026, 7, 18)
ENGINE = GexEngine()


def chain(strikes, oi, iv) -> pd.DataFrame:
    return pd.DataFrame(
        {"strike": strikes, "openInterest": oi, "impliedVolatility": iv}
    )


def test_black_scholes_gamma_hand_computed_case() -> None:
    """Caso manual del spec 2.1.6 nivel 2: S=100, K=100, T=30/365,
    sigma=0.20, r=0.04. d1 = 0.08600, phi(d1) = 0.397470,
    gamma = 0.397470 / (100 * 0.2 * 0.28674) = 0.069311."""
    gamma = black_scholes_gamma(100.0, 100.0, 30 / 365, 0.20, 0.04)
    assert gamma == pytest.approx(0.06931, rel=1e-3)


def test_gamma_symmetric_in_moneyness_direction() -> None:
    atm = black_scholes_gamma(100.0, 100.0, 0.1, 0.2)
    otm = black_scholes_gamma(100.0, 130.0, 0.1, 0.2)
    assert atm > otm  # la gamma es máxima cerca del dinero


def test_gamma_invalid_inputs_raise() -> None:
    with pytest.raises(DataQualityError):
        black_scholes_gamma(0.0, 100.0, 0.1, 0.2)
    with pytest.raises(DataQualityError):
        black_scholes_gamma(100.0, 100.0, 0.1, 0.0)


def test_gex_strike_formula_reproduces_manual_case() -> None:
    """1000 contratos de call ATM del caso manual:
    GEX = 1000 × 100 × 0.069311 × 100² × 0.01 = 693,110 USD/1%."""
    gamma = black_scholes_gamma(100.0, 100.0, 30 / 365, 0.20)
    expected = 1000 * CONTRACT_MULTIPLIER * gamma * 100.0 * 100.0 * 0.01
    calls = chain([100.0], [1000], [0.20])
    puts = chain([100.0], [0], [0.20])
    exp_date = date(2026, 8, 17)  # 30 días desde AS_OF
    profile = compute_gex_profile(
        "AAPL", 100.0, {exp_date.isoformat(): (calls, puts)}, AS_OF
    )
    assert profile.call_gex == pytest.approx(expected, rel=1e-6)
    assert profile.put_gex == 0.0
    assert profile.net_gex == pytest.approx(expected, rel=1e-6)


def test_sign_convention_calls_positive_puts_negative() -> None:
    calls = chain([100.0], [1000], [0.20])
    puts = chain([100.0], [1000], [0.20])
    exp = date(2026, 8, 17).isoformat()
    profile = compute_gex_profile("AAPL", 100.0, {exp: (calls, puts)}, AS_OF)
    assert profile.call_gex > 0
    assert profile.put_gex < 0
    # mismo OI y misma IV en el mismo strike: se cancelan
    assert profile.net_gex == pytest.approx(0.0, abs=1e-9)
    assert profile.normalized_balance == pytest.approx(0.0, abs=1e-9)


def test_walls_and_flip() -> None:
    exp = date(2026, 8, 7).isoformat()
    calls = chain([105.0, 110.0], [5000, 1000], [0.2, 0.2])
    puts = chain([90.0, 95.0], [4000, 1000], [0.25, 0.22])
    profile = compute_gex_profile("AAPL", 100.0, {exp: (calls, puts)}, AS_OF)
    assert profile.call_wall == 105.0
    assert profile.put_wall == 90.0
    # gamma flip: por debajo dominan puts (negativo), por encima calls
    assert profile.gamma_flip == 105.0


def test_expired_and_far_expirations_ignored() -> None:
    calls = chain([100.0], [1000], [0.2])
    puts = chain([100.0], [0], [0.2])
    chains = {
        date(2026, 7, 1).isoformat(): (calls, puts),  # vencida
        date(2026, 12, 18).isoformat(): (calls, puts),  # > 45 días
    }
    with pytest.raises(DataSourceError, match="sin datos"):
        compute_gex_profile("AAPL", 100.0, chains, AS_OF)


def test_zero_oi_and_bad_iv_skipped() -> None:
    exp = date(2026, 8, 7).isoformat()
    calls = chain([95.0, 100.0, 105.0], [0, 1000, 500], [0.2, 0.0, 0.2])
    puts = chain([100.0], [0], [0.2])
    profile = compute_gex_profile("AAPL", 100.0, {exp: (calls, puts)}, AS_OF)
    # solo el strike 105 sobrevive (95 sin OI, 100 con IV 0)
    assert profile.call_wall == 105.0


def test_engine_score_and_result() -> None:
    exp = date(2026, 8, 7).isoformat()
    calls = chain([100.0, 105.0], [8000, 4000], [0.2, 0.21])
    puts = chain([90.0, 95.0], [1000, 500], [0.25, 0.22])
    result, profile = ENGINE.score_ticker(
        "AAPL", 100.0, {exp: (calls, puts)}, AS_OF
    )
    assert result.engine == EngineName.GEX
    assert 0 < result.score <= 1.0  # dominan las calls: balance positivo
    assert result.score == pytest.approx(profile.normalized_balance)
    assert "call wall" in result.justification
