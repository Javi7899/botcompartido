"""Análisis de variantes del motor Series Temporales SOLO en desarrollo.

Tras el FALLA del AR(5) en el backtest pre-registrado (holdout t=0.71),
este script evalúa variantes más simples exclusivamente en el periodo de
desarrollo (< 2022). El holdout queda intacto hasta la confirmación
one-shot de la variante elegida. Requiere red.
"""

import sys
from math import tanh

import numpy as np

from quantbot.backtest.runner import (
    HORIZON,
    development_only,
    download_universe_closes,
)
from quantbot.backtest.walkforward import evaluate_engine, period_stats
from quantbot.engines.timeseries import (
    FIT_WINDOW,
    MIN_BARS,
    forecast_cumulative_return,
)


def log_returns(closes: list[float]) -> np.ndarray:
    window = np.asarray(closes[-(FIT_WINDOW + 1) :], dtype=float)
    if len(closes) < MIN_BARS or np.any(window <= 0):
        raise ValueError("historia insuficiente o precios no positivos")
    return np.diff(np.log(window))


def make_ar_variant(order: int):
    def score(ticker: str, closes: list[float]) -> float:
        predicted = forecast_cumulative_return(
            log_returns(closes), order=order
        )
        return tanh(25.0 * predicted)

    return score


def drift_only(ticker: str, closes: list[float]) -> float:
    returns = log_returns(closes)
    return tanh(25.0 * float(np.mean(returns)) * HORIZON)


VARIANTS = {
    "AR(1)": make_ar_variant(1),
    "AR(2)": make_ar_variant(2),
    "AR(5) [original]": make_ar_variant(5),
    "solo deriva (media 500d)": drift_only,
}


def main() -> int:
    development = development_only(download_universe_closes())
    print(
        f"Periodo de desarrollo: {development.index[0].date()} -> "
        f"{development.index[-1].date()} ({len(development)} sesiones)"
    )
    print(
        f"{'variante':<26} {'fechas':>6} {'IC medio':>9} {'t-stat':>7} "
        f"{'%IC>0':>6} {'L-S':>8}"
    )
    for label, fn in VARIANTS.items():
        results = evaluate_engine(
            development, fn, horizon=HORIZON, min_history=MIN_BARS
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
