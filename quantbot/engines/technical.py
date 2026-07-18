"""Technical engine (spec 2.1.1) — motor 1 de la tabla 0.0.

VERSION 2 (simplificado tras el backtest pre-registrado, ver
docs/BACKTEST_MOTOR_TECNICO.md): score = tanh(5 * (close / SMA200 - 1)),
puro seguimiento de tendencia con parámetros fijos (nada ajustado).

Historia de la simplificación (protocolo regla 3 del spec): la v1
combinaba tendencia + momentum 12-1 + reversión RSI14 y FALLÓ el criterio
pre-registrado en holdout (t=0.98). El análisis por componentes SOLO en
desarrollo (2012-2021, scripts/analyze_technical_components.py) mostró la
reversión RSI como ruido dañino (IC -0.007) y tendencia ~ momentum en IC
(t=1.01 ambas) con mayor spread económico en tendencia (+0.54% vs +0.23%
por 21 sesiones). Se eligió tendencia pura con el holdout aún intacto; la
confirmación one-shot en holdout quedó registrada en el informe.

Las funciones de momentum y RSI se conservan en el módulo porque el
análisis de componentes las usa y porque son candidatas si el paper
trading reabre la cuestión con evidencia nueva.
"""

from collections.abc import Sequence
from math import tanh
from typing import ClassVar

from quantbot.db.models import EngineName
from quantbot.engines.base import EngineResult, InsufficientDataError, SignalEngine

SMA_WINDOW = 200
MOMENTUM_LONG = 252
MOMENTUM_SKIP = 21
RSI_WINDOW = 14
MIN_BARS = MOMENTUM_LONG + 10

TREND_SCALE = 5.0
MOMENTUM_SCALE = 3.0

DATA_SOURCE = "daily_bars.adj_close (yfinance)"


def sma(values: Sequence[float], window: int) -> float:
    if len(values) < window:
        raise InsufficientDataError(
            f"SMA{window}: solo {len(values)} valores disponibles"
        )
    tail = values[-window:]
    return sum(tail) / window


def momentum_12_1(closes: Sequence[float]) -> float:
    """Return over [t-252, t-21]."""
    if len(closes) < MOMENTUM_LONG:
        raise InsufficientDataError(
            f"momentum 12-1: solo {len(closes)} valores disponibles"
        )
    past = closes[-MOMENTUM_LONG]
    recent = closes[-MOMENTUM_SKIP]
    if past <= 0:
        raise InsufficientDataError(f"precio no positivo en t-252: {past}")
    return recent / past - 1


def cutler_rsi(closes: Sequence[float], window: int = RSI_WINDOW) -> float:
    """RSI with simple (not Wilder-smoothed) averages over the last window."""
    if len(closes) < window + 1:
        raise InsufficientDataError(
            f"RSI{window}: solo {len(closes)} valores disponibles"
        )
    deltas = [
        closes[i] - closes[i - 1]
        for i in range(len(closes) - window, len(closes))
    ]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


class TechnicalEngine(SignalEngine):
    """v2: tendencia pura close vs SMA200 (ver docstring del módulo)."""

    name: ClassVar[EngineName] = EngineName.TECHNICAL
    version: ClassVar[str] = "2.0-trend-only"

    def score(self, ticker: str, adj_closes: Sequence[float]) -> EngineResult:
        if len(adj_closes) < MIN_BARS:
            raise InsufficientDataError(
                f"{ticker}: {len(adj_closes)} barras < mínimo {MIN_BARS}"
            )
        if any(c <= 0 for c in adj_closes[-MIN_BARS:]):
            raise InsufficientDataError(
                f"{ticker}: precios no positivos en la ventana de cálculo"
            )

        close = adj_closes[-1]
        average = sma(adj_closes, SMA_WINDOW)
        deviation = close / average - 1
        score = max(-1.0, min(1.0, tanh(TREND_SCALE * deviation)))
        justification = (
            f"[{self.version}] close {close:.2f} vs SMA{SMA_WINDOW} "
            f"{average:.2f} ({deviation:+.1%})"
        )
        return EngineResult(
            engine=self.name,
            ticker=ticker,
            score=score,
            justification=justification,
            data_source=DATA_SOURCE,
        )
