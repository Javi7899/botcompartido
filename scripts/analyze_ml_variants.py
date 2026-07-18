"""Análisis de variantes del motor ML SOLO en desarrollo (< 2022).

Tras el FALLA del XGBoost v1 (holdout t=0.39), se comparan exclusivamente
en desarrollo dos simplificaciones. El holdout queda intacto hasta la
confirmación one-shot de la elegida. Requiere red.

Variantes (deliberadamente solo dos, para limitar los caminos de
decisión):
1. Ridge lineal sobre las mismas features (menos varianza que árboles).
2. XGBoost extra-regularizado (depth 2, min_child_weight 200, eta 0.03).
"""

import sys

import numpy as np
import pandas as pd

from quantbot.backtest.ml_walkforward import evaluate_ml
from quantbot.backtest.runner import (
    HORIZON,
    development_only,
    download_universe_data,
)
from quantbot.backtest.walkforward import period_stats
from quantbot.engines.ml_features import FEATURE_COLUMNS
from quantbot.engines.ml_linear import RidgeModel
from quantbot.engines.ml_xgboost import MLEngine, XGBoostModel

MIN_HISTORY = 260
RETRAIN_EVERY = 126
MIN_TRAIN = 10_000


class ExtraRegXGB:
    """XGBoost con regularización reforzada (params fijados aquí, a priori)."""

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        import xgboost as xgb

        train_matrix = xgb.DMatrix(
            X[list(FEATURE_COLUMNS)].values, label=y.values
        )
        self._booster = xgb.train(
            {
                "objective": "reg:squarederror",
                "max_depth": 2,
                "eta": 0.03,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "min_child_weight": 200,
                "lambda": 5.0,
                "tree_method": "hist",
                "seed": 42,
            },
            train_matrix,
            num_boost_round=300,
        )

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        import xgboost as xgb

        return self._booster.predict(
            xgb.DMatrix(X[list(FEATURE_COLUMNS)].values)
        )


VARIANTS = {
    "XGBoost v1 [referencia]": lambda: MLEngine(XGBoostModel()),
    "Ridge lineal": RidgeModel,
    "XGBoost extra-reg": ExtraRegXGB,
}


def main() -> int:
    data = download_universe_data(("Adj Close", "Volume"))
    closes = development_only(data["Adj Close"])
    volumes = development_only(data["Volume"])
    print(
        f"Periodo de desarrollo: {closes.index[0].date()} -> "
        f"{closes.index[-1].date()} ({len(closes)} sesiones)"
    )
    print(
        f"{'variante':<26} {'fechas':>6} {'IC medio':>9} {'t-stat':>7} "
        f"{'%IC>0':>6} {'L-S':>8}"
    )
    for label, factory in VARIANTS.items():
        results = evaluate_ml(
            closes,
            volumes,
            factory,
            horizon=HORIZON,
            min_history=MIN_HISTORY,
            retrain_every=RETRAIN_EVERY,
            min_train_samples=MIN_TRAIN,
        )
        stats = period_stats(label, results)
        print(
            f"{label:<26} {stats.n_dates:>6} {stats.mean_ic:>+9.4f} "
            f"{stats.t_stat:>+7.2f} {stats.pct_ic_positive:>6.0%} "
            f"{stats.mean_ls_spread:>+8.4f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
