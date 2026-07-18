import numpy as np
import pandas as pd
import pytest

from quantbot.engines.ml_features import FEATURE_COLUMNS
from quantbot.engines.ml_linear import RidgeModel


def planted_xy(n: int = 5000, noise: float = 0.001, seed: int = 9):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        rng.normal(0, 1, (n, len(FEATURE_COLUMNS))),
        columns=list(FEATURE_COLUMNS),
    )
    y = 0.2 * X["ret_21d"] - 0.1 * X["vol_63d"] + rng.normal(0, noise, n)
    return X, y


def test_recovers_planted_linear_signal() -> None:
    X, y = planted_xy()
    model = RidgeModel(ridge_lambda=1.0)
    model.fit(X, y)
    predictions = model.predict(X)
    assert np.corrcoef(predictions, y)[0, 1] > 0.98


def test_scale_invariance_via_standardization() -> None:
    X, y = planted_xy()
    scaled = X.copy()
    scaled["ret_21d"] *= 1000.0  # cambiar unidades no debe cambiar el modelo
    a, b = RidgeModel(), RidgeModel()
    a.fit(X, y)
    b.fit(scaled, y)
    scaled_test = X.iloc[:100].copy()
    scaled_test["ret_21d"] *= 1000.0
    np.testing.assert_allclose(
        a.predict(X.iloc[:100]), b.predict(scaled_test), rtol=1e-6
    )


def test_higher_lambda_shrinks_predictions() -> None:
    X, y = planted_xy(noise=0.1)
    weak, strong = RidgeModel(ridge_lambda=0.1), RidgeModel(ridge_lambda=1e6)
    weak.fit(X, y)
    strong.fit(X, y)
    spread_weak = np.std(weak.predict(X))
    spread_strong = np.std(strong.predict(X))
    assert spread_strong < spread_weak * 0.1


def test_predict_before_fit_raises() -> None:
    X, _ = planted_xy(100)
    with pytest.raises(ValueError, match="sin entrenar"):
        RidgeModel().predict(X)


def test_constant_feature_does_not_crash() -> None:
    X, y = planted_xy()
    X["volume_ratio"] = 0.0  # std cero: no debe dividir por cero
    model = RidgeModel()
    model.fit(X, y)
    assert np.isfinite(model.predict(X.iloc[:10])).all()
