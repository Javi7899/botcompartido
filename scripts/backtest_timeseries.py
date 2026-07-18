"""Backtest walk-forward del motor Series Temporales (gate de Fase 3.3).

    python scripts/backtest_timeseries.py

Mismo protocolo pre-registrado que todos los motores de precio
(quantbot/backtest/runner.py): holdout desde 2022, PASA t>=2 /
MARGINAL 1-2 / FALLA <1. Requiere red.
"""

import sys

from quantbot.backtest.runner import run_price_engine_backtest
from quantbot.engines.timeseries import (
    AR_ORDER,
    FIT_WINDOW,
    FORECAST_STEPS,
    MIN_BARS,
    TimeSeriesEngine,
)


def main() -> int:
    engine = TimeSeriesEngine()

    def score_fn(ticker: str, history: list[float]) -> float:
        return engine.score(ticker, history).score

    run_price_engine_backtest(
        engine_label="time_series",
        score_fn=score_fn,
        min_history=MIN_BARS,
        report_title=(
            "Backtest walk-forward — Motor Series Temporales (Fase 3.3)"
        ),
        report_path="docs/BACKTEST_MOTOR_SERIES_TEMPORALES.md",
        design_notes=[
            f"AR({AR_ORDER}) sobre retornos log diarios, OLS sobre las "
            f"últimas {FIT_WINDOW} sesiones (equivalente ARIMA({AR_ORDER},0,0)).",
            f"Forecast iterado {FORECAST_STEPS} pasos; score = tanh(25 × "
            "retorno log acumulado predicho).",
            f"Versión del motor: {TimeSeriesEngine.version}. Parámetros "
            "fijos, nada ajustado.",
        ],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
