"""Combine per-engine scores into a final weighted score per asset.

Uses the weights from the hierarchical weighter (Capa 2.2). The result
feeds the LLM supervisor (Capa 2.3) and then Black-Litterman (Fase 6).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from quantbot.db.models import EngineName


@dataclass(frozen=True)
class CombinedScore:
    ticker: str
    score: float  # en [-1, 1]
    contributions: dict[EngineName, float]  # peso × score por motor
    engines_used: int


def combine_scores(
    ticker: str,
    engine_scores: Mapping[EngineName, float],
    engine_weights: Mapping[EngineName, float],
) -> CombinedScore:
    """Weighted sum of engine scores. Only engines present in BOTH maps
    contribute; missing engines are simply absent (never imputed)."""
    contributions: dict[EngineName, float] = {}
    total = 0.0
    for engine, weight in engine_weights.items():
        if engine not in engine_scores or weight == 0.0:
            continue
        score = engine_scores[engine]
        if not -1.0 <= score <= 1.0:
            raise ValueError(
                f"{ticker}/{engine}: score fuera de rango ({score})"
            )
        contribution = weight * score
        contributions[engine] = contribution
        total += contribution

    return CombinedScore(
        ticker=ticker,
        score=max(-1.0, min(1.0, total)),
        contributions=contributions,
        engines_used=len(contributions),
    )
