import numpy as np
import pandas as pd
import pytest

from quantbot.meta.correlations import correlation_matrix, factor_exposure


def make_closes(n: int = 200, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n)
    market = rng.normal(0.0005, 0.01, n)
    # AAA y BBB comparten factor de mercado; CCC es independiente
    aaa = market + rng.normal(0, 0.002, n)
    bbb = market + rng.normal(0, 0.002, n)
    ccc = rng.normal(0.0005, 0.01, n)
    frame = {}
    for name, ret in (("AAA", aaa), ("BBB", bbb), ("CCC", ccc)):
        frame[name] = 100 * np.cumprod(1 + ret)
    return pd.DataFrame(frame, index=dates)


def test_correlation_matrix_shape_and_diagonal() -> None:
    corr = correlation_matrix(make_closes())
    assert corr.shape == (3, 3)
    assert corr.loc["AAA", "AAA"] == pytest.approx(1.0)


def test_correlated_pair_detected() -> None:
    corr = correlation_matrix(make_closes())
    assert corr.loc["AAA", "BBB"] > 0.8
    assert abs(corr.loc["AAA", "CCC"]) < 0.5


def test_factor_exposure_groups() -> None:
    corr = correlation_matrix(make_closes())
    groups = factor_exposure(corr, threshold=0.7)
    assert "BBB" in groups["AAA"]
    assert "CCC" not in groups["AAA"]


def test_single_ticker_raises() -> None:
    with pytest.raises(ValueError, match="al menos 2"):
        correlation_matrix(make_closes().iloc[:, :1])


def test_insufficient_overlap_is_nan() -> None:
    closes = make_closes(50)
    corr = correlation_matrix(closes, min_overlap=100)
    assert pd.isna(corr.loc["AAA", "BBB"])
