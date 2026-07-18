import pytest

from quantbot.db.models import EngineName
from quantbot.engines import InsufficientDataError, TechnicalEngine
from quantbot.engines.technical import MIN_BARS, cutler_rsi, momentum_12_1, sma

ENGINE = TechnicalEngine()


def geometric(n: int, daily: float, start: float = 100.0) -> list[float]:
    prices = [start]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + daily))
    return prices


def test_uptrend_scores_positive() -> None:
    result = ENGINE.score("AAPL", geometric(300, 0.002))
    assert result.engine == EngineName.TECHNICAL
    assert result.score > 0.1
    assert "SMA200" in result.justification
    assert "2.0-trend-only" in result.justification


def test_downtrend_scores_negative() -> None:
    result = ENGINE.score("AAPL", geometric(300, -0.002))
    assert result.score < -0.1


def test_flat_series_scores_zero() -> None:
    result = ENGINE.score("AAPL", [100.0] * 300)
    assert result.score == pytest.approx(0.0)


def test_recent_drop_below_sma_scores_negative() -> None:
    # 290 sesiones planas y caída del 15% en las últimas 10: bajo la SMA200.
    prices = [100.0] * 290 + [100.0 - 1.5 * i for i in range(1, 11)]
    result = ENGINE.score("AAPL", prices)
    assert result.score < 0.0


def test_score_bounded() -> None:
    explosive = geometric(300, 0.05)
    assert -1.0 <= ENGINE.score("AAPL", explosive).score <= 1.0


def test_insufficient_data_raises() -> None:
    with pytest.raises(InsufficientDataError, match="mínimo"):
        ENGINE.score("AAPL", geometric(100, 0.001))


def test_non_positive_price_raises() -> None:
    prices = geometric(MIN_BARS, 0.001)
    prices[-5] = 0.0
    with pytest.raises(InsufficientDataError, match="no positivos"):
        ENGINE.score("AAPL", prices)


def test_sma_known_value() -> None:
    assert sma([1.0, 2.0, 3.0, 4.0], 2) == 3.5


def test_momentum_known_value() -> None:
    prices = [100.0] * 300
    prices[-252] = 80.0
    prices[-21] = 96.0
    assert momentum_12_1(prices) == pytest.approx(0.2)


def test_rsi_extremes_and_neutral() -> None:
    up = [float(i) for i in range(100, 120)]
    down = [float(i) for i in range(120, 100, -1)]
    flat = [100.0] * 20
    alternating = [100.0 + (i % 2) for i in range(21)]
    assert cutler_rsi(up) == 100.0
    assert cutler_rsi(down) == 0.0
    assert cutler_rsi(flat) == 50.0
    assert cutler_rsi(alternating) == pytest.approx(50.0)


def test_rsi_insufficient_raises() -> None:
    with pytest.raises(InsufficientDataError):
        cutler_rsi([100.0] * 10)
