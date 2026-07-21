"""Black-Litterman optimizer (spec 3).

Combines a market-equilibrium prior (implied by market-cap weights) with
the engine scores as "views" to produce target portfolio weights — a
mathematically coherent blend of signal and market equilibrium, instead of
equal-weight or ad-hoc allocation.

Construction (standard reference BL, with score-as-tilt views):
- Prior implied excess returns: π = δ Σ w_mkt.
- Views: one absolute view per asset (P = identity), expressed as a TILT on
  the prior: q_i = π_i + view_scale · s_i. A zero score therefore states
  "expected return = prior" → no change; a positive score tilts the view
  above the prior, a negative one below it. This avoids the classic bug
  where score 0 is misread as "the return is exactly zero" and drags the
  posterior down. View uncertainty Ω is diagonal: weaker evidence → larger
  variance → the view moves the posterior less.
- Posterior: E[R] = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ [(τΣ)⁻¹π + PᵀΩ⁻¹Q].
- Target weights: w = (δΣ)⁻¹ E[R], then long-only clipped and normalized.

All parameters are explicit and documented; nothing is fit to a backtest
(the supervisor and weights are validated in paper trading).
"""

from collections.abc import Sequence

import numpy as np

# Defaults (documented, parametrizable). risk_aversion δ ≈ 2.5 is the
# classic Black-Litterman market value; tau scales prior uncertainty.
DEFAULT_RISK_AVERSION = 2.5
DEFAULT_TAU = 0.05
DEFAULT_VIEW_SCALE = 0.03  # un score de 1.0 ≈ +3% de retorno esperado/mes


def market_prior(
    cov: np.ndarray, market_weights: np.ndarray, risk_aversion: float
) -> np.ndarray:
    """Implied equilibrium excess returns π = δ Σ w_mkt."""
    return risk_aversion * cov @ market_weights


def views_from_scores(
    scores: Sequence[float],
    evidence_weights: Sequence[float] | None = None,
    *,
    prior: Sequence[float] | None = None,
    cov: np.ndarray | None = None,
    tau: float = DEFAULT_TAU,
    view_scale: float = DEFAULT_VIEW_SCALE,
    base_uncertainty: float = 0.02,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build (P, Q, Ω) with one absolute view per asset, as a TILT on the
    prior: q_i = π_i + view_scale · s_i.

    Passing ``prior`` is what makes a zero score mean "no opinion" (the view
    equals the prior, so the posterior is unchanged) instead of "the return
    is exactly zero". Without a prior the tilt is applied around zero, which
    is only correct when the caller has already centred the scores.

    ``evidence_weights`` in (0, 1] scales confidence: higher → smaller view
    variance (the view is trusted more). Defaults to equal confidence.

    Ω follows the He-Litterman convention: Ω = diag(P τΣ Pᵀ) / confidence.
    Scaling the view variance to the PRIOR's own uncertainty is what gives
    the views material weight — a fixed absolute Ω (e.g. 0.02) is swamped by
    (τΣ)⁻¹ for typical τ, and the engine scores would barely move the
    posterior. With confidence 1 the view and the prior carry equal weight.
    """
    n = len(scores)
    if n == 0:
        raise ValueError("se necesita al menos un activo con score")
    if evidence_weights is None:
        evidence_weights = [1.0] * n
    if len(evidence_weights) != n:
        raise ValueError("scores y evidence_weights de distinta longitud")
    base = np.zeros(n) if prior is None else np.asarray(prior, float)
    if len(base) != n:
        raise ValueError("prior de longitud distinta a scores")

    P = np.eye(n)
    Q = base + view_scale * np.asarray(scores, dtype=float)
    if cov is not None:
        # He-Litterman: la varianza de la view sigue la del prior.
        view_variance = np.diag(P @ (tau * np.asarray(cov, float)) @ P.T)
    else:
        view_variance = np.full(n, base_uncertainty)
    omega = np.diag(
        [v / max(w, 1e-6) for v, w in zip(view_variance, evidence_weights)]
    )
    return P, Q, omega


def posterior_returns(
    cov: np.ndarray,
    prior: np.ndarray,
    P: np.ndarray,
    Q: np.ndarray,
    omega: np.ndarray,
    *,
    tau: float = DEFAULT_TAU,
) -> np.ndarray:
    """Black-Litterman posterior expected returns."""
    tau_cov_inv = np.linalg.inv(tau * cov)
    omega_inv = np.linalg.inv(omega)
    precision = tau_cov_inv + P.T @ omega_inv @ P
    mean = tau_cov_inv @ prior + P.T @ omega_inv @ Q
    return np.linalg.solve(precision, mean)


def black_litterman_weights(
    cov: np.ndarray,
    market_weights: np.ndarray,
    scores: Sequence[float],
    evidence_weights: Sequence[float] | None = None,
    *,
    risk_aversion: float = DEFAULT_RISK_AVERSION,
    tau: float = DEFAULT_TAU,
    view_scale: float = DEFAULT_VIEW_SCALE,
    long_only: bool = True,
) -> np.ndarray:
    """Target portfolio weights from BL posterior. Long-only by default
    (the account holds no shorts); weights clipped at 0 and normalized to
    sum to 1. If every weight clips to 0, returns all-cash (zeros)."""
    n = len(scores)
    if cov.shape != (n, n):
        raise ValueError(f"cov {cov.shape} incompatible con {n} activos")
    if len(market_weights) != n:
        raise ValueError("market_weights de longitud distinta a scores")

    prior = market_prior(cov, np.asarray(market_weights, float), risk_aversion)
    P, Q, omega = views_from_scores(
        scores,
        evidence_weights,
        prior=prior,
        cov=cov,
        tau=tau,
        view_scale=view_scale,
    )
    posterior = posterior_returns(cov, prior, P, Q, omega, tau=tau)
    raw = np.linalg.solve(risk_aversion * cov, posterior)

    if long_only:
        raw = np.clip(raw, 0.0, None)
    total = raw.sum()
    if total <= 0:
        return np.zeros(n)
    return raw / total
