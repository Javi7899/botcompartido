"""Time-series engine (spec 2.1.3) — motor 3 de la tabla 0.0.

VERSION 2: AR(1) sobre retornos logarítmicos diarios, estimado por OLS
sobre las últimas 500 sesiones (equivalente a un ARIMA(1,0,0) con término
constante; la estimación OLS es asintóticamente equivalente a la MLE
condicional, determinista y rápida). El forecast se itera 21 pasos y el
retorno log acumulado predicho se mapea a score con tanh.

Historia de la simplificación (protocolo regla 3, igual que el motor
Técnico): la v1 AR(5) FALLÓ el backtest pre-registrado (holdout t=0.71
pese a dev t=1.92). El análisis de variantes SOLO en desarrollo
(scripts/analyze_timeseries_variants.py) dio: AR(1) t=2.40, AR(2) t=2.35,
deriva-pura t=2.36, AR(5) t=2.18 — se eligió AR(1) por ser la más simple
y la de mayor evidencia, con el holdout intacto. La confirmación one-shot
quedó registrada en docs/BACKTEST_MOTOR_SERIES_TEMPORALES.md.

Parámetros FIJOS (nada ajustado): orden 1, ventana 500, horizonte 21,
escala tanh 25.
"""

from collections.abc import Sequence
from math import isfinite, tanh
from typing import ClassVar

import numpy as np

from quantbot.db.models import EngineName
from quantbot.engines.base import EngineResult, InsufficientDataError, SignalEngine

AR_ORDER = 1
FIT_WINDOW = 500
FORECAST_STEPS = 21
SCORE_SCALE = 25.0
MIN_BARS = 260  # mismo mínimo que el motor Técnico: evaluación comparable

DATA_SOURCE = "daily_bars.adj_close (yfinance)"


def fit_ar_ols(returns: np.ndarray, order: int) -> tuple[float, np.ndarray]:
    """OLS fit of r_t = c + sum(phi_i * r_{t-i}) + e. Returns (c, phis)."""
    if len(returns) < order + 10:
        raise InsufficientDataError(
            f"AR({order}): {len(returns)} retornos insuficientes"
        )
    if float(np.std(returns)) < 1e-12:
        # Retornos constantes: sin dinámica AR que estimar, pero la deriva
        # (media) sí es información — descartarla anularía la predicción de
        # una serie con crecimiento perfectamente estable.
        return float(np.mean(returns)), np.zeros(order)
    rows = len(returns) - order
    design = np.ones((rows, order + 1))
    for lag in range(1, order + 1):
        design[:, lag] = returns[order - lag : order - lag + rows]
    target = returns[order:]
    solution, *_ = np.linalg.lstsq(design, target, rcond=None)
    return float(solution[0]), solution[1:]


def forecast_cumulative_return(
    returns: np.ndarray, *, order: int = AR_ORDER, steps: int = FORECAST_STEPS
) -> float:
    """Iterated multi-step forecast; returns predicted cumulative log return."""
    intercept, phis = fit_ar_ols(returns, order)
    history = list(returns[-order:])
    total = 0.0
    for _ in range(steps):
        prediction = intercept + sum(
            phi * value for phi, value in zip(phis, reversed(history))
        )
        total += prediction
        history.append(prediction)
        history.pop(0)
    if not isfinite(total):
        raise InsufficientDataError(
            "forecast no finito (serie degenerada o coeficientes inestables)"
        )
    return total


class TimeSeriesEngine(SignalEngine):
    name: ClassVar[EngineName] = EngineName.TIME_SERIES
    version: ClassVar[str] = "2.0-ar1-ols"

    def score(self, ticker: str, adj_closes: Sequence[float]) -> EngineResult:
        if len(adj_closes) < MIN_BARS:
            raise InsufficientDataError(
                f"{ticker}: {len(adj_closes)} barras < mínimo {MIN_BARS}"
            )
        window = np.asarray(adj_closes[-(FIT_WINDOW + 1) :], dtype=float)
        if np.any(window <= 0):
            raise InsufficientDataError(
                f"{ticker}: precios no positivos en la ventana de cálculo"
            )
        returns = np.diff(np.log(window))
        predicted = forecast_cumulative_return(returns)
        score = max(-1.0, min(1.0, tanh(SCORE_SCALE * predicted)))
        justification = (
            f"[{self.version}] AR({AR_ORDER}) sobre {len(returns)} retornos; "
            f"retorno log predicho a {FORECAST_STEPS} sesiones: "
            f"{predicted:+.4f}"
        )
        return EngineResult(
            engine=self.name,
            ticker=ticker,
            score=score,
            justification=justification,
            data_source=DATA_SOURCE,
        )
