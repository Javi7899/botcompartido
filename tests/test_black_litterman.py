import numpy as np
import pytest

from quantbot.portfolio.black_litterman import (
    black_litterman_weights,
    market_prior,
    posterior_returns,
    views_from_scores,
)


def simple_cov(n: int = 3, var: float = 0.04, corr: float = 0.2) -> np.ndarray:
    cov = np.full((n, n), corr * var)
    np.fill_diagonal(cov, var)
    return cov


def test_market_prior_shape_and_sign() -> None:
    cov = simple_cov()
    w = np.array([0.4, 0.3, 0.3])
    prior = market_prior(cov, w, 2.5)
    assert prior.shape == (3,)
    assert np.all(prior > 0)  # pesos positivos, covarianza positiva


def test_no_views_recovers_market_weights() -> None:
    """Con views nulas (scores 0), los pesos BL ≈ pesos de mercado."""
    cov = simple_cov()
    market = np.array([0.4, 0.35, 0.25])
    weights = black_litterman_weights(cov, market, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(weights, market, atol=1e-6)


def test_positive_view_tilts_toward_asset() -> None:
    cov = simple_cov()
    market = np.array([1 / 3, 1 / 3, 1 / 3])
    weights = black_litterman_weights(cov, market, [0.8, 0.0, 0.0])
    # el activo con view positiva pesa más que en el mercado
    assert weights[0] > 1 / 3
    assert weights[0] > weights[1]


def test_strongly_negative_views_go_all_cash() -> None:
    cov = simple_cov()
    market = np.array([1 / 3, 1 / 3, 1 / 3])
    # views lo bastante negativas para hundir el posterior bajo cero:
    # long-only + retorno esperado negativo => cartera vacía
    weights = black_litterman_weights(
        cov, market, [-1.0, -1.0, -1.0], view_scale=0.10
    )
    assert weights.sum() == pytest.approx(0.0)


def test_uniform_mild_negative_views_keep_relative_weights() -> None:
    """Separación de responsabilidades: BL fija pesos RELATIVOS; reducir la
    exposición total ante un edge pobre es trabajo de Kelly (fase Kelly),
    no de BL. Views moderadamente negativas e iguales no vacían la cartera:
    dejan los pesos relativos intactos."""
    cov = simple_cov()
    market = np.array([1 / 3, 1 / 3, 1 / 3])
    weights = black_litterman_weights(cov, market, [-0.5, -0.5, -0.5])
    np.testing.assert_allclose(weights, market, atol=1e-6)


def test_weights_sum_to_one_when_invested() -> None:
    cov = simple_cov(4)
    market = np.array([0.25, 0.25, 0.25, 0.25])
    weights = black_litterman_weights(cov, market, [0.5, 0.2, -0.1, 0.3])
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights >= 0)


def test_evidence_weight_scales_view_impact() -> None:
    cov = simple_cov()
    market = np.array([1 / 3, 1 / 3, 1 / 3])
    strong = black_litterman_weights(
        cov, market, [1.0, 0.0, 0.0], evidence_weights=[1.0, 1.0, 1.0]
    )
    weak = black_litterman_weights(
        cov, market, [1.0, 0.0, 0.0], evidence_weights=[0.05, 1.0, 1.0]
    )
    # más confianza en la view → mayor desviación del mercado
    assert strong[0] > weak[0]


def test_posterior_between_prior_and_view() -> None:
    cov = simple_cov(1, var=0.04)
    prior = np.array([0.02])
    P, Q, omega = views_from_scores([1.0], view_scale=0.10)  # view = 0.10
    posterior = posterior_returns(cov, prior, P, Q, omega, tau=0.05)
    assert 0.02 < posterior[0] < 0.10


def test_dimension_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        black_litterman_weights(simple_cov(3), np.array([0.5, 0.5]), [0.1, 0.2])
