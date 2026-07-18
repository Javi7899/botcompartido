import numpy as np
import pytest

from quantbot.db.models import EngineName
from quantbot.engines import InsufficientDataError
from quantbot.engines.timeseries import (
    TimeSeriesEngine,
    fit_ar_ols,
    forecast_cumulative_return,
)

ENGINE = TimeSeriesEngine()


def ar1_series(phi: float, n: int = 600, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 0.01, n)
    returns = np.zeros(n)
    for i in range(1, n):
        returns[i] = phi * returns[i - 1] + noise[i]
    return returns


def test_fit_recovers_ar1_coefficient() -> None:
    returns = ar1_series(0.5)
    intercept, phis = fit_ar_ols(returns, 5)
    assert phis[0] == pytest.approx(0.5, abs=0.1)
    assert abs(intercept) < 0.002
    assert all(abs(p) < 0.15 for p in phis[1:])


def test_constant_series_predicts_zero() -> None:
    intercept, phis = fit_ar_ols(np.zeros(300), 5)
    assert intercept == 0.0
    assert forecast_cumulative_return(np.zeros(300)) == 0.0


def test_positive_drift_predicts_positive_return() -> None:
    # Deriva claramente dominante sobre el ruido (0.003 vs sigma 0.005):
    # la media muestral es positiva con margen y el forecast debe serlo.
    rng = np.random.default_rng(7)
    returns = rng.normal(0.003, 0.005, 600)
    assert forecast_cumulative_return(returns) > 0


def test_fit_insufficient_raises() -> None:
    with pytest.raises(InsufficientDataError):
        fit_ar_ols(np.zeros(10), 5)


def test_engine_score_uptrend_positive() -> None:
    prices = [100.0 * 1.001**i for i in range(600)]
    result = ENGINE.score("AAPL", prices)
    assert result.engine == EngineName.TIME_SERIES
    assert result.score > 0.3
    assert "AR(1)" in result.justification
    assert "2.0-ar1-ols" in result.justification


def test_engine_score_downtrend_negative() -> None:
    prices = [100.0 * 0.999**i for i in range(600)]
    assert ENGINE.score("AAPL", prices).score < -0.3


def test_engine_flat_scores_zero() -> None:
    assert ENGINE.score("AAPL", [100.0] * 600).score == pytest.approx(0.0)


def test_engine_insufficient_data_raises() -> None:
    with pytest.raises(InsufficientDataError, match="mínimo"):
        ENGINE.score("AAPL", [100.0] * 100)


def test_engine_non_positive_price_raises() -> None:
    prices = [100.0] * 600
    prices[-50] = -1.0
    with pytest.raises(InsufficientDataError, match="no positivos"):
        ENGINE.score("AAPL", prices)


def test_score_bounded_on_explosive_series() -> None:
    prices = [100.0 * 1.05**i for i in range(600)]
    assert -1.0 <= ENGINE.score("AAPL", prices).score <= 1.0
