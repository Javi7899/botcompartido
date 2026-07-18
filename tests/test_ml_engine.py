import numpy as np
import pandas as pd
import pytest

from quantbot.backtest.ml_walkforward import evaluate_ml
from quantbot.data.errors import DataQualityError
from quantbot.db.models import EngineName
from quantbot.engines.ml_features import FEATURE_COLUMNS, HORIZON
from quantbot.engines.ml_xgboost import MLEngine


def synthetic_xy(n: int = 12_000, seed: int = 5) -> tuple[pd.DataFrame, pd.Series]:
    """Señal plantada: el target depende de ret_5d y vol_21d."""
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        rng.normal(0, 1, (n, len(FEATURE_COLUMNS))), columns=list(FEATURE_COLUMNS)
    )
    y = 0.1 * X["ret_5d"] - 0.05 * X["vol_21d"] + rng.normal(0, 0.05, n)
    return X, y


def test_fit_and_predict_learns_planted_signal() -> None:
    X, y = synthetic_xy()
    train_X, test_X = X.iloc[:10_000], X.iloc[10_000:]
    train_y, test_y = y.iloc[:10_000], y.iloc[10_000:]
    engine = MLEngine()  # v2: ridge por defecto
    engine.fit(train_X, train_y)
    predictions = engine.predict(test_X)
    correlation = np.corrcoef(predictions, test_y)[0, 1]
    assert correlation > 0.5


def test_xgboost_model_also_learns_planted_signal() -> None:
    from quantbot.engines.ml_xgboost import XGBoostModel

    X, y = synthetic_xy()
    engine = MLEngine(XGBoostModel())
    engine.fit(X.iloc[:10_000], y.iloc[:10_000])
    predictions = engine.predict(X.iloc[10_000:])
    assert np.corrcoef(predictions, y.iloc[10_000:])[0, 1] > 0.5


def test_fit_deterministic() -> None:
    X, y = synthetic_xy()
    a, b = MLEngine(), MLEngine()
    a.fit(X, y)
    b.fit(X, y)
    sample = X.iloc[:50]
    assert np.array_equal(a.predict(sample), b.predict(sample))


def test_fit_too_few_samples_raises() -> None:
    X, y = synthetic_xy(500)
    with pytest.raises(DataQualityError, match="mínimo"):
        MLEngine().fit(X, y)


def test_predict_before_fit_raises() -> None:
    X, _ = synthetic_xy(100)
    with pytest.raises(DataQualityError, match="sin entrenar"):
        MLEngine().predict(X)


def test_wrong_columns_raise() -> None:
    X, y = synthetic_xy()
    renamed = X.rename(columns={"ret_5d": "typo"})
    with pytest.raises(DataQualityError, match="columnas"):
        MLEngine().fit(renamed, y)


def test_score_universe_contract() -> None:
    X, y = synthetic_xy()
    engine = MLEngine()
    engine.fit(X, y)
    today = X.iloc[:15].copy()
    today.index = [f"T{i:02d}" for i in range(15)]
    results = engine.score_universe(today)
    assert len(results) == 15
    assert all(r.engine == EngineName.ML_XGBOOST for r in results)
    scores = sorted(r.score for r in results)
    assert scores[0] == pytest.approx(-1.0)
    assert scores[-1] == pytest.approx(1.0)


class SpyModel:
    """Registra las fechas de entrenamiento para verificar el embargo."""

    max_train_dates: list[pd.Timestamp] = []

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        SpyModel.max_train_dates.append(X.index.get_level_values(0).max())

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X["ret_5d"].to_numpy()


def test_evaluate_ml_respects_embargo() -> None:
    rng = np.random.default_rng(11)
    n, tickers = 800, [f"T{i:02d}" for i in range(20)]
    dates = pd.bdate_range("2022-01-03", periods=n)
    closes = pd.DataFrame(
        {t: 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n)) for t in tickers},
        index=dates,
    )
    volumes = pd.DataFrame(
        {t: rng.integers(1_000_000, 2_000_000, n).astype(float) for t in tickers},
        index=dates,
    )
    SpyModel.max_train_dates = []
    results = evaluate_ml(
        closes,
        volumes,
        SpyModel,
        horizon=HORIZON,
        min_history=300,
        retrain_every=126,
        min_train_samples=500,
    )
    assert len(results) > 5
    assert SpyModel.max_train_dates, "el spy nunca se entrenó"
    # Embargo: en cada reentrenamiento en la fecha de evaluación i, la
    # última muestra de entrenamiento debe ser <= fecha[i - HORIZON].
    eval_positions = list(range(300, n - HORIZON, HORIZON))
    retrain_positions = eval_positions[:: 126 // HORIZON]
    for max_train_date, position in zip(
        SpyModel.max_train_dates, retrain_positions
    ):
        assert max_train_date <= dates[position - HORIZON]
