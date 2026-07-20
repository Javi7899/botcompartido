"""News engine (spec 2.1.7) — motor 7 de la tabla 0.0. LIVE-ONLY (spec 0.1).

Único motor con excepción temporal deliberada (spec 1): usa noticias hasta
el momento exacto de ejecución, no solo T-1. Cada predicción persiste con
las noticias que la sustentan; el archivo point-in-time de news_items
(acumulándose desde Fase 2) permitirá evaluarlo honestamente.

Diseño v1 (parámetros FIJOS): sentimiento por léxico financiero embebido,
inspirado en las listas Loughran-McDonald (el estándar académico para
texto financiero; los léxicos genéricos fallan en finanzas — "liability"
no es negativo en un balance).

- Score por titular: (positivas − negativas) / (positivas + negativas).
- Score del ticker: media ponderada por recencia (semivida 24 h desde la
  publicación hasta el momento de ejecución) de los titulares de las
  últimas 48 h. Sin titulares → 0 (sin noticias = neutral).
- Limitaciones documentadas: sin manejo de negaciones ni contexto macro
  (v2 candidata: integrar los feeds macro ya almacenados). El supervisor
  LLM (Capa 2.3) es quien lee el texto completo con contexto.
"""

import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from math import tanh
from typing import ClassVar

from quantbot.data.news import NewsItemRecord
from quantbot.db.models import EngineName
from quantbot.engines.base import EngineResult

DATA_SOURCE = "RSS con timestamp exacto (yahoo_ticker_rss); léxico financiero"

WINDOW_HOURS = 48
HALF_LIFE_HOURS = 24.0
INTENSITY_SCALE = 2.0  # tanh(2·media): 2-3 titulares claros saturan

POSITIVE_WORDS = frozenset(
    """
    beat beats beating exceeded exceeds surpass surpassed record records
    strong strength growth growing grew profit profitable profits gain
    gains gained rally rallies surge surged surges soar soared soars jump
    jumped jumps rise rises rose rising upgrade upgraded upgrades
    outperform outperforms raised raises boost boosted boosts buyback
    dividend dividends breakthrough approval approved wins win won award
    awarded expansion expand expands innovative bullish momentum improved
    improves improving optimistic upbeat guidance-raise accelerate
    accelerates accelerating milestone partnership
    """.split()
)

NEGATIVE_WORDS = frozenset(
    """
    miss missed misses shortfall weak weakness decline declined declines
    drop dropped drops fall falls fell falling plunge plunged plunges
    slump slumped crash crashed tumble tumbled sink sank sinks downgrade
    downgraded downgrades underperform lawsuit lawsuits sued sues fraud
    probe probes investigation investigating recall recalls layoff
    layoffs bankruptcy bankrupt default defaults warning warns warned cut
    cuts cutting loss losses losing bearish concern concerns concerned
    risk risks risky fears fear fined fine penalty penalties delay
    delayed delays halt halted suspends suspended scandal breach
    """.split()
)

_TOKEN_PATTERN = re.compile(r"[a-z']+")


def headline_sentiment(title: str) -> float | None:
    """(pos − neg) / (pos + neg) en [−1, 1]; None si no hay palabras del
    léxico (titular no informativo para este motor)."""
    tokens = _TOKEN_PATTERN.findall(title.lower())
    positives = sum(1 for t in tokens if t in POSITIVE_WORDS)
    negatives = sum(1 for t in tokens if t in NEGATIVE_WORDS)
    total = positives + negatives
    if total == 0:
        return None
    return (positives - negatives) / total


class NewsEngine:
    name: ClassVar[EngineName] = EngineName.MACRO_NEWS
    version: ClassVar[str] = "1.0-lexicon-lm"

    def score_ticker(
        self,
        ticker: str,
        items: Sequence[NewsItemRecord],
        as_of: datetime,
    ) -> EngineResult:
        if as_of.tzinfo is None:
            raise ValueError("as_of debe ser timezone-aware")
        window_start = as_of - timedelta(hours=WINDOW_HOURS)
        weighted_sum = 0.0
        weight_total = 0.0
        scored = neutral = 0
        for item in items:
            if item.published_at < window_start or item.published_at > as_of:
                continue
            sentiment = headline_sentiment(item.title)
            if sentiment is None:
                neutral += 1
                continue
            age_hours = (as_of - item.published_at).total_seconds() / 3600.0
            weight = 0.5 ** (age_hours / HALF_LIFE_HOURS)
            weighted_sum += sentiment * weight
            weight_total += weight
            scored += 1

        if scored == 0:
            return EngineResult(
                engine=self.name,
                ticker=ticker,
                score=0.0,
                justification=(
                    f"[{self.version}] sin titulares con carga de "
                    f"sentimiento en {WINDOW_HOURS} h "
                    f"({neutral} neutrales)"
                ),
                data_source=DATA_SOURCE,
            )
        average = weighted_sum / weight_total
        score = max(-1.0, min(1.0, tanh(INTENSITY_SCALE * average)))
        return EngineResult(
            engine=self.name,
            ticker=ticker,
            score=score,
            justification=(
                f"[{self.version}] {scored} titulares con señal en "
                f"{WINDOW_HOURS} h ({neutral} neutrales); sentimiento "
                f"medio ponderado por recencia {average:+.2f}"
            ),
            data_source=DATA_SOURCE,
        )
