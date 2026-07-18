import pytest

from quantbot.data.errors import DataQualityError
from quantbot.db.models import EngineName
from quantbot.engines.fundamental import (
    FundamentalEngine,
    FundamentalMetrics,
    centered_percentiles,
)

ENGINE = FundamentalEngine()


def metrics(ticker: str, ey=None, roe=None, margin=None, growth=None):
    return FundamentalMetrics(
        ticker=ticker,
        earnings_yield=ey,
        return_on_equity=roe,
        profit_margin=margin,
        revenue_growth=growth,
    )


def build_universe(n: int = 12) -> list[FundamentalMetrics]:
    """Ticker T00 es el peor en todo; T11 el mejor en todo."""
    return [
        metrics(
            f"T{i:02d}",
            ey=0.01 + 0.005 * i,
            roe=0.05 + 0.02 * i,
            margin=0.05 + 0.01 * i,
            growth=-0.05 + 0.02 * i,
        )
        for i in range(n)
    ]


def test_best_and_worst_get_extreme_scores() -> None:
    results, skipped = ENGINE.score_universe(build_universe())
    assert skipped == {}
    by_ticker = {r.ticker: r for r in results}
    assert by_ticker["T11"].score == pytest.approx(1.0)
    assert by_ticker["T00"].score == pytest.approx(-1.0)
    assert by_ticker["T05"].score == pytest.approx(-1 / 11 * 1, abs=0.1)
    assert all(r.engine == EngineName.FUNDAMENTAL for r in results)
    assert "NO point-in-time" in results[0].data_source


def test_ticker_with_too_few_metrics_skipped() -> None:
    universe = build_universe() + [metrics("POOR", ey=0.05)]
    results, skipped = ENGINE.score_universe(universe)
    assert "POOR" in skipped
    assert "1 métricas" in skipped["POOR"]
    assert all(r.ticker != "POOR" for r in results)


def test_partial_metrics_still_scored() -> None:
    universe = build_universe() + [metrics("HALF", ey=0.10, roe=0.50)]
    results, skipped = ENGINE.score_universe(universe)
    half = next(r for r in results if r.ticker == "HALF")
    # el mejor earnings yield y el mejor ROE del universo -> score alto
    assert half.score > 0.9
    assert "earnings_yield" in half.justification
    assert "revenue_growth" not in half.justification


def test_too_few_usable_tickers_raises() -> None:
    with pytest.raises(DataQualityError, match="mínimo 10"):
        ENGINE.score_universe(build_universe(5))


def test_from_yf_info_parsing() -> None:
    m = FundamentalMetrics.from_yf_info(
        "AAPL",
        {
            "trailingPE": 25.0,
            "returnOnEquity": 1.20,
            "profitMargins": 0.26,
            "revenueGrowth": 0.08,
        },
    )
    assert m.earnings_yield == pytest.approx(0.04)
    assert m.available_metrics() == 4


def test_from_yf_info_negative_pe_and_missing() -> None:
    m = FundamentalMetrics.from_yf_info(
        "LOSS", {"trailingPE": -12.0, "profitMargins": "n/a"}
    )
    assert m.earnings_yield is None
    assert m.profit_margin is None
    assert m.available_metrics() == 0


def test_centered_percentiles_bounds_and_ties() -> None:
    import pandas as pd

    values = pd.Series({"A": 1.0, "B": 2.0, "C": 2.0, "D": 3.0})
    ranks = centered_percentiles(values)
    assert ranks["A"] == pytest.approx(-1.0)
    assert ranks["D"] == pytest.approx(1.0)
    assert ranks["B"] == ranks["C"] == pytest.approx(0.0)
