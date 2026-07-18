"""Análisis de componentes del motor Técnico SOLO en desarrollo (< 2022).

Protocolo anti-overfitting: tras el FALLA del compuesto en el backtest
pre-registrado, la simplificación se elige mirando exclusivamente el
periodo de desarrollo. El holdout (>= 2022) queda intacto y solo se usará
UNA vez para confirmar la variante elegida (scripts/backtest_technical.py
con la variante final). Requiere red.
"""

import sys
from datetime import date
from math import tanh

import pandas as pd

from quantbot.backtest.walkforward import evaluate_engine, period_stats
from quantbot.engines.technical import (
    MIN_BARS,
    MOMENTUM_SCALE,
    SMA_WINDOW,
    TREND_SCALE,
    cutler_rsi,
    momentum_12_1,
    sma,
)
from scripts.backtest_technical import SPLIT_DATE, download_universe_closes

HORIZON = 21


def trend_score(ticker: str, closes: list[float]) -> float:
    if len(closes) < MIN_BARS:
        raise ValueError("historia insuficiente")
    return tanh(TREND_SCALE * (closes[-1] / sma(closes, SMA_WINDOW) - 1))


def momentum_score(ticker: str, closes: list[float]) -> float:
    if len(closes) < MIN_BARS:
        raise ValueError("historia insuficiente")
    return tanh(MOMENTUM_SCALE * momentum_12_1(closes))


def reversion_score(ticker: str, closes: list[float]) -> float:
    if len(closes) < MIN_BARS:
        raise ValueError("historia insuficiente")
    return (50.0 - cutler_rsi(closes)) / 50.0


def trend_momentum_score(ticker: str, closes: list[float]) -> float:
    return (trend_score(ticker, closes) + momentum_score(ticker, closes)) / 2


VARIANTS = {
    "solo tendencia (SMA200)": trend_score,
    "solo momentum 12-1": momentum_score,
    "solo reversión RSI14": reversion_score,
    "tendencia + momentum": trend_momentum_score,
}


def main() -> int:
    closes = download_universe_closes()
    # Solo desarrollo: el holdout no se toca en este análisis.
    development = closes[closes.index < pd.Timestamp(SPLIT_DATE).tz_localize(closes.index.tz)]
    print(
        f"Periodo de desarrollo: {development.index[0].date()} -> "
        f"{development.index[-1].date()} ({len(development)} sesiones)"
    )
    print(f"{'variante':<28} {'fechas':>6} {'IC medio':>9} {'t-stat':>7} {'%IC>0':>6} {'L-S':>8}")
    for label, fn in VARIANTS.items():
        results = evaluate_engine(
            development, fn, horizon=HORIZON, min_history=MIN_BARS
        )
        stats = period_stats(label, results)
        print(
            f"{label:<28} {stats.n_dates:>6} {stats.mean_ic:>+9.4f} "
            f"{stats.t_stat:>+7.2f} {stats.pct_ic_positive:>6.0%} "
            f"{stats.mean_ls_spread:>+8.4f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
