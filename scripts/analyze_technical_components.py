"""Análisis de componentes del motor Técnico SOLO en desarrollo (< 2022).

Protocolo anti-overfitting: tras el FALLA del compuesto v1 en el backtest
pre-registrado, la simplificación se eligió mirando exclusivamente el
periodo de desarrollo. El holdout (>= 2022) quedó intacto y solo se usó
UNA vez para confirmar la variante elegida (v2 tendencia pura, ver
docs/BACKTEST_MOTOR_TECNICO.md). Requiere red.
"""

import sys
from math import tanh

from quantbot.backtest.runner import (
    HORIZON,
    development_only,
    download_universe_closes,
)
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
    development = development_only(download_universe_closes())
    print(
        f"Periodo de desarrollo: {development.index[0].date()} -> "
        f"{development.index[-1].date()} ({len(development)} sesiones)"
    )
    header = (
        f"{'variante':<28} {'fechas':>6} {'IC medio':>9} {'t-stat':>7} "
        f"{'%IC>0':>6} {'L-S':>8}"
    )
    print(header)
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
