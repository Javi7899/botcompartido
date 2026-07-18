from datetime import date

import pandas as pd
import pytest

from quantbot.backtest.walkforward import (
    evaluate_engine,
    period_stats,
    spearman_ic,
    split_report,
    tercile_spread,
)

TICKERS = [f"T{i:02d}" for i in range(20)]


def test_spearman_perfect_and_inverse() -> None:
    scores = {t: float(i) for i, t in enumerate(TICKERS)}
    returns_up = {t: float(i) * 0.01 for i, t in enumerate(TICKERS)}
    returns_down = {t: -float(i) * 0.01 for i, t in enumerate(TICKERS)}
    assert spearman_ic(scores, returns_up) == pytest.approx(1.0)
    assert spearman_ic(scores, returns_down) == pytest.approx(-1.0)


def test_spearman_small_section_is_none() -> None:
    scores = {t: 1.0 for t in TICKERS[:5]}
    assert spearman_ic(scores, scores) is None


def test_tercile_spread_known() -> None:
    scores = {t: float(i) for i, t in enumerate(TICKERS[:18])}
    returns = {t: float(i) for i, t in enumerate(TICKERS[:18])}
    # top 6: media 14.5; bottom 6: media 2.5
    assert tercile_spread(scores, returns) == pytest.approx(12.0)


def synthetic_prices(n_days: int = 400) -> pd.DataFrame:
    """20 tickers con drifts distintos y deterministas."""
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    data = {}
    for i, ticker in enumerate(TICKERS):
        daily = 0.0005 * (i - 10)  # drift creciente con i
        prices = [100.0]
        for _ in range(n_days - 1):
            prices.append(prices[-1] * (1 + daily))
        data[ticker] = prices
    return pd.DataFrame(data, index=dates)


def recent_return_score(ticker: str, closes: list[float]) -> float:
    return closes[-1] / closes[-60] - 1


def test_evaluate_engine_detects_persistent_drift() -> None:
    prices = synthetic_prices()
    results = evaluate_engine(
        prices, recent_return_score, horizon=21, min_history=80
    )
    # el drift persiste: el score por retorno reciente predice el futuro
    assert results["ic"].mean() > 0.9
    assert (results["ls_spread"] > 0).all()


def test_evaluate_engine_no_dates_raises() -> None:
    prices = synthetic_prices(90)
    with pytest.raises(ValueError, match="ninguna fecha"):
        evaluate_engine(
            prices, recent_return_score, horizon=21, min_history=80
        )


def test_period_stats_and_split() -> None:
    dates = pd.bdate_range("2024-01-01", periods=24, freq="21B")
    results = pd.DataFrame(
        {"ic": [0.1] * 12 + [0.2] * 12, "ls_spread": [0.01] * 24}, index=dates
    )
    stats = period_stats("todo", results)
    assert stats.n_dates == 24
    assert stats.mean_ic == pytest.approx(0.15)
    assert stats.t_stat > 10
    assert stats.pct_ic_positive == 1.0

    report = split_report(
        "technical", results, horizon=21, split_date=date(2025, 1, 1)
    )
    assert report.development.n_dates + report.holdout.n_dates == 24
    assert report.development.n_dates >= 8
    assert report.holdout.n_dates >= 8


def test_period_stats_too_few_raises() -> None:
    results = pd.DataFrame(
        {"ic": [0.1] * 3, "ls_spread": [0.0] * 3},
        index=pd.bdate_range("2024-01-01", periods=3),
    )
    with pytest.raises(ValueError, match="insuficiente"):
        period_stats("x", results)
