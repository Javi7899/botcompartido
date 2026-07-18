"""Backtest walk-forward del motor ML/XGBoost (gate de Fase 3.4).

    python scripts/backtest_ml.py

Mismo protocolo pre-registrado que el resto de motores, con la diferencia
de que aquí el modelo SÍ se entrena: reentrenamiento expansivo cada 126
sesiones con embargo de 21 (ninguna etiqueta solapa la fecha de
predicción). Hiperparámetros fijos a priori — nada se tuneó contra este
backtest. Requiere red.
"""

import sys

from quantbot.backtest.ml_walkforward import evaluate_ml
from quantbot.backtest.runner import (
    HORIZON,
    SPLIT_DATE,
    download_universe_data,
    verdict,
    write_markdown_report,
)
from quantbot.backtest.walkforward import split_report
from quantbot.engines.ml_features import FEATURE_COLUMNS
from quantbot.engines.ml_linear import RIDGE_LAMBDA
from quantbot.engines.ml_xgboost import (
    MIN_TRAIN_SAMPLES,
    MLEngine,
    NUM_BOOST_ROUND,
    XGB_PARAMS,
)

MIN_HISTORY = 260
RETRAIN_EVERY = 126


def main() -> int:
    data = download_universe_data(("Adj Close", "Volume"))
    results = evaluate_ml(
        data["Adj Close"],
        data["Volume"],
        MLEngine,
        horizon=HORIZON,
        min_history=MIN_HISTORY,
        retrain_every=RETRAIN_EVERY,
        min_train_samples=MIN_TRAIN_SAMPLES,
    )
    report = split_report(
        "ml_xgboost", results, horizon=HORIZON, split_date=SPLIT_DATE
    )
    final = verdict(report.holdout.mean_ic, report.holdout.t_stat)
    write_markdown_report(
        report=report,
        final=final,
        report_title="Backtest walk-forward — Motor ML/XGBoost (Fase 3.4)",
        report_path="docs/BACKTEST_MOTOR_ML.md",
        design_notes=[
            f"{len(FEATURE_COLUMNS)} features OHLCV T-1: {', '.join(FEATURE_COLUMNS)}.",
            "Target: retorno forward 21d demeaned transversalmente "
            "(rendimiento relativo, no dirección de mercado).",
            f"Reentrenamiento expansivo cada {RETRAIN_EVERY} sesiones con "
            f"embargo de {HORIZON}; mínimo {MIN_TRAIN_SAMPLES:,} muestras.",
            f"Modelo v2: Ridge lineal (lambda fijo {RIDGE_LAMBDA}), elegido "
            "en el protocolo de simplificación tras el FALLA del XGBoost v1 "
            f"(params v1: {NUM_BOOST_ROUND} rondas, {XGB_PARAMS}).",
            f"Versión del motor: {MLEngine.version}.",
        ],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
