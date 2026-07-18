"""ML engine (spec 2.1.4) — motor 4 de la tabla 0.0.

Predice el retorno forward 21d demeaned transversalmente (rendimiento
RELATIVO entre pares, no dirección del mercado) a partir de las features
T-1 de ml_features.

VERSION 2: el modelo por defecto es RIDGE LINEAL (ml_linear.RidgeModel).
Historia (protocolo regla 3): el XGBoost v1 con hiperparámetros fijos
FALLÓ el backtest pre-registrado (holdout t=0.39 pese a dev t=1.91). El
análisis de variantes SOLO en desarrollo (scripts/analyze_ml_variants.py)
dio: Ridge t=3.30 (IC +0.082), XGBoost v1 t=1.90, XGBoost extra-reg
t=1.51 — lo lineal domina a los árboles con esta relación señal/ruido.
La confirmación one-shot en holdout está en docs/BACKTEST_MOTOR_ML.md.

XGBoostModel se conserva como implementación alternativa para el análisis
histórico y por si el paper trading reabre la comparación.

Anti-overfitting:
- Parámetros del modelo FIJOS a priori (lambda ridge 10; params XGB
  documentados abajo). PROHIBIDO tunearlos contra el backtest.
- Reentrenamiento walk-forward estricto con embargo de 21 sesiones
  (quantbot/backtest/ml_walkforward.py).
"""

from typing import ClassVar

import numpy as np
import pandas as pd

from quantbot.data.errors import DataQualityError
from quantbot.db.models import EngineName
from quantbot.engines.base import EngineResult
from quantbot.engines.fundamental import centered_percentiles
from quantbot.engines.ml_features import FEATURE_COLUMNS

DATA_SOURCE = "features OHLCV T-1 (yfinance) + XGBoost walk-forward"

MIN_TRAIN_SAMPLES = 10_000

# Fijados a priori; ver docstring. API nativa de xgboost (sin dependencia
# de scikit-learn). seed para reproducibilidad.
NUM_BOOST_ROUND = 200
XGB_PARAMS: dict = {
    "objective": "reg:squarederror",
    "max_depth": 3,
    "eta": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 50,
    "lambda": 1.0,
    "tree_method": "hist",
    "seed": 42,
}


class XGBoostModel:
    """Implementación XGBoost (v1, superada por Ridge en desarrollo)."""

    def __init__(self) -> None:
        self._booster = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        import xgboost as xgb

        train_matrix = xgb.DMatrix(
            X[list(FEATURE_COLUMNS)].values, label=y.values
        )
        self._booster = xgb.train(
            XGB_PARAMS, train_matrix, num_boost_round=NUM_BOOST_ROUND
        )

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        import xgboost as xgb

        if self._booster is None:
            raise ValueError("XGBoostModel sin entrenar")
        return self._booster.predict(
            xgb.DMatrix(X[list(FEATURE_COLUMNS)].values)
        )


class MLEngine:
    """Cross-sectional engine: needs a fitted model plus one date's
    features for the whole universe (like the fundamental engine, the
    prediction only means something relative to peers).

    The model implementation is injectable; the default is the v2 Ridge.
    """

    name: ClassVar[EngineName] = EngineName.ML_XGBOOST
    version: ClassVar[str] = "2.0-ridge-linear"

    def __init__(self, model=None) -> None:
        from quantbot.engines.ml_linear import RidgeModel

        self._model = model if model is not None else RidgeModel()
        self._fitted = False
        self._trained_samples = 0

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(self, features: pd.DataFrame, target: pd.Series) -> None:
        if list(features.columns) != list(FEATURE_COLUMNS):
            raise DataQualityError(
                f"columnas inesperadas: {list(features.columns)}"
            )
        if not features.index.equals(target.index):
            raise DataQualityError("features y target desalineados")
        if len(features) < MIN_TRAIN_SAMPLES:
            raise DataQualityError(
                f"{len(features)} muestras de entrenamiento < mínimo "
                f"{MIN_TRAIN_SAMPLES}"
            )
        self._model.fit(features, target)
        self._fitted = True
        self._trained_samples = len(features)

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise DataQualityError("modelo sin entrenar")
        if list(features.columns) != list(FEATURE_COLUMNS):
            raise DataQualityError(
                f"columnas inesperadas: {list(features.columns)}"
            )
        return self._model.predict(features)

    def score_universe(
        self, features_today: pd.DataFrame
    ) -> list[EngineResult]:
        """``features_today``: frame indexed by ticker with FEATURE_COLUMNS,
        computed with data up to T-1. Scores = centered percentile of the
        model's predicted relative return."""
        predictions = pd.Series(
            self.predict(features_today), index=features_today.index
        )
        if predictions.nunique() < 2:
            raise DataQualityError(
                "predicciones degeneradas (sin variación transversal)"
            )
        ranks = centered_percentiles(predictions)
        results = []
        for ticker in features_today.index:
            score = max(-1.0, min(1.0, float(ranks[ticker])))
            results.append(
                EngineResult(
                    engine=self.name,
                    ticker=ticker,
                    score=score,
                    justification=(
                        f"[{self.version}] retorno relativo 21d predicho "
                        f"{predictions[ticker]:+.4f} (rank {score:+.2f}; "
                        f"modelo con {self._trained_samples:,} muestras)"
                    ),
                    data_source=DATA_SOURCE,
                )
            )
        return results
