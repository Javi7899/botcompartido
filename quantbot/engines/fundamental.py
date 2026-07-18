"""Fundamental engine (spec 2.1.2) — motor 2 de la tabla 0.0.

LIVE-ONLY: la conclusión de Fase 2 (docs/FUENTES_DATOS.md) es que los
fundamentales de yfinance NO son point-in-time, así que este motor está
prohibido de backtest histórico. Opera solo en vivo, persiste sus
predicciones a diario y su validación real es el paper trading (spec 0.1).
Arranca con peso bayesiano inicial conservador.

Diseño (fijo, nada ajustado): score transversal por ranking dentro del
universo — un fundamental solo es "bueno" o "malo" relativo a los pares.
Cuatro métricas con igual peso, cada una convertida a percentil centrado
en [-1, 1] entre los tickers que la tienen:

- earnings_yield  = 1 / trailingPE (mayor = más barato = mejor)
- return_on_equity (mayor = mejor)
- profit_margin    (mayor = mejor)
- revenue_growth   (mayor = mejor)

Un ticker necesita >= 2 métricas disponibles para recibir score; si el
universo utilizable cae por debajo de 10 tickers, el motor falla ruidosa-
mente (algo pasa con la fuente).
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

import pandas as pd
from loguru import logger
from pydantic import BaseModel, ConfigDict

from quantbot.data.errors import DataQualityError, DataSourceError
from quantbot.db.models import EngineName
from quantbot.engines.base import EngineResult

DATA_SOURCE = "yfinance Ticker.info (snapshot, NO point-in-time)"

METRIC_FIELDS = (
    "earnings_yield",
    "return_on_equity",
    "profit_margin",
    "revenue_growth",
)
MIN_METRICS_PER_TICKER = 2
MIN_USABLE_TICKERS = 10


class FundamentalMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    earnings_yield: float | None = None
    return_on_equity: float | None = None
    profit_margin: float | None = None
    revenue_growth: float | None = None

    @classmethod
    def from_yf_info(cls, ticker: str, info: Mapping) -> "FundamentalMetrics":
        def as_float(key: str) -> float | None:
            value = info.get(key)
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                logger.warning(
                    "{}: campo {} no numérico ({!r}); se trata como ausente",
                    ticker,
                    key,
                    value,
                )
                return None

        trailing_pe = as_float("trailingPE")
        return cls(
            ticker=ticker,
            # PE negativo o cero: sin beneficios -> earnings yield ausente
            # (no un yield negativo gigante que rompería el ranking).
            earnings_yield=1.0 / trailing_pe
            if trailing_pe and trailing_pe > 0
            else None,
            return_on_equity=as_float("returnOnEquity"),
            profit_margin=as_float("profitMargins"),
            revenue_growth=as_float("revenueGrowth"),
        )

    def available_metrics(self) -> int:
        return sum(
            1 for f in METRIC_FIELDS if getattr(self, f) is not None
        )


def centered_percentiles(values: pd.Series) -> pd.Series:
    """Rank to [-1, 1]: best of n -> +1, worst -> -1, ties averaged."""
    n = len(values)
    if n < 2:
        raise DataQualityError(
            f"ranking imposible con {n} valores (mínimo 2)"
        )
    ranks = values.rank(method="average")
    return (ranks - (n + 1) / 2) / ((n - 1) / 2)


class FundamentalEngine:
    """Cross-sectional engine: scores the whole universe at once (unlike
    the price engines, a fundamental is only meaningful vs. peers)."""

    name: ClassVar[EngineName] = EngineName.FUNDAMENTAL
    version: ClassVar[str] = "1.0-cross-sectional-rank"

    def score_universe(
        self, metrics: Sequence[FundamentalMetrics]
    ) -> tuple[list[EngineResult], dict[str, str]]:
        """Returns (results, skipped) with skip reasons per ticker."""
        skipped: dict[str, str] = {}
        usable = []
        for m in metrics:
            if m.available_metrics() < MIN_METRICS_PER_TICKER:
                skipped[m.ticker] = (
                    f"solo {m.available_metrics()} métricas disponibles "
                    f"(mínimo {MIN_METRICS_PER_TICKER})"
                )
            else:
                usable.append(m)
        if len(usable) < MIN_USABLE_TICKERS:
            raise DataQualityError(
                f"solo {len(usable)} tickers con fundamentales utilizables "
                f"(mínimo {MIN_USABLE_TICKERS}); revisar la fuente"
            )

        contributions: dict[str, dict[str, float]] = {
            m.ticker: {} for m in usable
        }
        for field in METRIC_FIELDS:
            with_metric = {
                m.ticker: getattr(m, field)
                for m in usable
                if getattr(m, field) is not None
            }
            if len(with_metric) < 2:
                continue
            percentiles = centered_percentiles(pd.Series(with_metric))
            for ticker, percentile in percentiles.items():
                contributions[ticker][field] = float(percentile)

        results = []
        for m in usable:
            parts = contributions[m.ticker]
            score = max(-1.0, min(1.0, sum(parts.values()) / len(parts)))
            detail = ", ".join(
                f"{field}={getattr(m, field):.3f} (rank {value:+.2f})"
                for field, value in parts.items()
            )
            results.append(
                EngineResult(
                    engine=self.name,
                    ticker=m.ticker,
                    score=score,
                    justification=f"[{self.version}] {detail}",
                    data_source=DATA_SOURCE,
                )
            )
        return results, skipped


def fetch_universe_fundamentals(
    tickers: Sequence[str], *, max_failure_fraction: float = 0.2
) -> list[FundamentalMetrics]:
    """Fetch yfinance info for the universe. Individual ticker failures are
    tolerated up to ``max_failure_fraction`` (logged loudly); beyond that
    the source itself is considered broken and the fetch raises."""
    import yfinance as yf

    metrics: list[FundamentalMetrics] = []
    failures: dict[str, str] = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            if not info or not isinstance(info, dict):
                raise DataSourceError("info vacío")
            metrics.append(FundamentalMetrics.from_yf_info(ticker, info))
        except Exception as exc:  # noqa: BLE001 - se re-lanza si son demasiados
            failures[ticker] = str(exc)
            logger.error("fundamentales de {} fallaron: {}", ticker, exc)
    if len(failures) > max_failure_fraction * len(tickers):
        raise DataSourceError(
            f"{len(failures)}/{len(tickers)} tickers fallaron al descargar "
            f"fundamentales: {failures}"
        )
    return metrics
