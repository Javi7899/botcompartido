import pytest

from quantbot.portfolio.kelly import fractional_kelly_scale, portfolio_moments


def test_positive_edge_scales_exposure() -> None:
    # full kelly = 0.06/0.04 = 1.5; con fracción 0.35 → 0.525
    exposure = fractional_kelly_scale(0.06, 0.04, kelly_fraction=0.35)
    assert exposure == pytest.approx(0.525)


def test_capped_at_max_exposure() -> None:
    # full kelly enorme, pero sin apalancamiento
    exposure = fractional_kelly_scale(0.5, 0.04, kelly_fraction=0.5)
    assert exposure == 1.0


def test_non_positive_edge_is_cash() -> None:
    assert fractional_kelly_scale(0.0, 0.04) == 0.0
    assert fractional_kelly_scale(-0.02, 0.04) == 0.0


def test_non_positive_variance_is_cash() -> None:
    assert fractional_kelly_scale(0.05, 0.0) == 0.0


def test_fraction_reduces_exposure() -> None:
    quarter = fractional_kelly_scale(0.06, 0.04, kelly_fraction=0.25)
    half = fractional_kelly_scale(0.06, 0.04, kelly_fraction=0.50)
    assert half > quarter


def test_invalid_fraction_raises() -> None:
    with pytest.raises(ValueError):
        fractional_kelly_scale(0.05, 0.04, kelly_fraction=0.0)
    with pytest.raises(ValueError):
        fractional_kelly_scale(0.05, 0.04, kelly_fraction=1.5)


def test_portfolio_moments() -> None:
    import numpy as np

    weights = [0.5, 0.5]
    mu = [0.04, 0.06]
    cov = np.array([[0.04, 0.0], [0.0, 0.09]])
    expected_mu, var = portfolio_moments(weights, mu, cov)
    assert expected_mu == pytest.approx(0.05)
    assert var == pytest.approx(0.25 * 0.04 + 0.25 * 0.09)
