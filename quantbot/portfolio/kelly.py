"""Fractional Kelly sizing (spec 3).

Once Black-Litterman sets the RELATIVE weights between assets, Kelly sets
the TOTAL exposure of the portfolio (how much of the capital to deploy vs.
hold as cash), given the estimated edge and variance. Full Kelly over-
levers with imperfect probability estimates, so we use a fraction
(25-50%, parametrizable) — the classic fractional-Kelly discipline.

For a portfolio with expected excess return μ_p and variance σ²_p, the
Kelly-optimal exposure fraction is μ_p / σ²_p. We scale it by the Kelly
fraction and cap it at 1.0 (no leverage — the account is cash-only).
"""

DEFAULT_KELLY_FRACTION = 0.35  # dentro del rango 0.25-0.50 del spec
MAX_EXPOSURE = 1.0  # sin apalancamiento


def fractional_kelly_scale(
    expected_excess_return: float,
    variance: float,
    *,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_exposure: float = MAX_EXPOSURE,
) -> float:
    """Fraction of capital to deploy, in [0, max_exposure].

    A non-positive edge or non-positive variance → 0 exposure (stay in
    cash: no bet without a positive expected edge)."""
    if not 0 < kelly_fraction <= 1:
        raise ValueError(f"kelly_fraction fuera de (0, 1]: {kelly_fraction}")
    if expected_excess_return <= 0 or variance <= 0:
        return 0.0
    full_kelly = expected_excess_return / variance
    scaled = kelly_fraction * full_kelly
    return max(0.0, min(max_exposure, scaled))


def portfolio_moments(
    weights, expected_returns, cov
) -> tuple[float, float]:
    """(expected excess return, variance) of the weighted portfolio."""
    import numpy as np

    w = np.asarray(weights, float)
    mu = float(w @ np.asarray(expected_returns, float))
    var = float(w @ np.asarray(cov, float) @ w)
    return mu, var
