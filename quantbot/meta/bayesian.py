"""Hierarchical bayesian weighter (Capa 2.2, Enmienda 2).

Goal (from the spec): if the technical engine predicts AAPL better than the
fundamental engine, technical should weigh more *for AAPL*; and vice-versa
for NVDA — WITHOUT the ~250 free parameters of a pure per-asset weighter.

The mechanism is shrinkage on the information coefficient (IC):

1. Per engine, the IC is the correlation between the engine's score and the
   asset's forward return. We compute it globally (all assets pooled) and
   per asset.
2. The GLOBAL IC of an engine is itself shrunk toward a conservative prior
   IC (``prior_ic``), with the prior worth ``prior_strength`` pseudo-obs.
   Engines with no historical evidence (live-only: fundamental, insider,
   gex, news) therefore sit at their low prior until paper trading (Fase 8)
   accumulates observations.
3. The PER-ASSET IC is shrunk toward the engine's global IC, with the
   global worth ``asset_shrinkage`` pseudo-obs. Few asset observations ->
   per-asset weight ≈ global; many -> it moves toward the asset's own IC.
4. Raw weight = max(0, shrunk IC): an engine that does not predict (IC<=0)
   gets no weight. Weights are normalized per asset over the engines that
   apply to that asset (gex/insider are excluded where they have no datum —
   spec: no neutral imputation).

Everything is deterministic and unit-tested; nothing is fit against a
holdout here (the ICs come from the Fase 3 walk-forward for the
backtestable engines, and from paper trading for the rest).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from quantbot.db.models import EngineName

# Motores que NO aplican a todos los activos: se excluyen (no se imputan)
# de la normalización en los activos donde no hay observación (spec 2.2).
CONDITIONAL_ENGINES = frozenset({EngineName.GEX, EngineName.INSIDER})

DEFAULT_PRIOR_IC = 0.01  # prior conservador para motores sin evidencia
DEFAULT_PRIOR_STRENGTH = 100.0  # pseudo-obs del prior sobre el IC global
DEFAULT_ASSET_SHRINKAGE = 75.0  # pseudo-obs del global sobre el IC por activo
MIN_OBS_FOR_IC = 12  # por debajo, el IC muestral es demasiado ruidoso


@dataclass(frozen=True)
class Observation:
    """One realized (score, forward_return) pair for an engine on an asset."""

    engine: EngineName
    ticker: str
    score: float
    forward_return: float


def information_coefficient(pairs: Sequence[tuple[float, float]]) -> float | None:
    """Spearman rank correlation of (score, forward_return). None if fewer
    than MIN_OBS_FOR_IC pairs or no variation on either side."""
    if len(pairs) < MIN_OBS_FOR_IC:
        return None
    scores = [p[0] for p in pairs]
    returns = [p[1] for p in pairs]
    return _spearman(scores, returns)


def _rank(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average_rank
        i = j + 1
    return ranks


def _spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    ra, rb = _rank(a), _rank(b)
    n = len(ra)
    mean_a = sum(ra) / n
    mean_b = sum(rb) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb))
    var_a = sum((x - mean_a) ** 2 for x in ra)
    var_b = sum((y - mean_b) ** 2 for y in rb)
    if var_a <= 0 or var_b <= 0:
        return None
    return cov / (var_a**0.5 * var_b**0.5)


def shrink(
    sample: float | None,
    sample_n: float,
    prior: float,
    prior_strength: float,
) -> float:
    """Posterior mean of a shrinkage estimator. With sample=None (no data)
    returns the prior; otherwise the precision-weighted blend."""
    if sample is None or sample_n <= 0:
        return prior
    return (sample_n * sample + prior_strength * prior) / (
        sample_n + prior_strength
    )


@dataclass(frozen=True)
class EngineEvidence:
    """Accumulated evidence for one engine, ready to weight.

    ``prior_ic`` encodes how much a priori credibility the engine has:
    the technical engine carries its (marginal) backtest IC; the live-only
    engines carry a small conservative prior until paper trading fills in
    ``global_pairs`` / ``per_asset_pairs``.
    """

    engine: EngineName
    prior_ic: float = DEFAULT_PRIOR_IC
    global_pairs: list[tuple[float, float]] = field(default_factory=list)
    per_asset_pairs: dict[str, list[tuple[float, float]]] = field(
        default_factory=dict
    )

    def global_ic(self, prior_strength: float) -> float:
        sample = information_coefficient(self.global_pairs)
        return shrink(sample, len(self.global_pairs), self.prior_ic, prior_strength)

    def asset_ic(self, ticker: str, global_ic: float, asset_shrinkage: float) -> float:
        pairs = self.per_asset_pairs.get(ticker, [])
        sample = information_coefficient(pairs)
        return shrink(sample, len(pairs), global_ic, asset_shrinkage)


@dataclass(frozen=True)
class WeightResult:
    """Normalized weights per (ticker, engine) plus the raw shrunk ICs."""

    weights: dict[str, dict[EngineName, float]]
    shrunk_ic: dict[str, dict[EngineName, float]]
    global_ic: dict[EngineName, float]


class HierarchicalWeighter:
    def __init__(
        self,
        *,
        prior_strength: float = DEFAULT_PRIOR_STRENGTH,
        asset_shrinkage: float = DEFAULT_ASSET_SHRINKAGE,
    ) -> None:
        self.prior_strength = prior_strength
        self.asset_shrinkage = asset_shrinkage

    def compute(
        self,
        evidences: Iterable[EngineEvidence],
        tickers: Sequence[str],
        available: Mapping[str, set[EngineName]] | None = None,
    ) -> WeightResult:
        """Weights for each ticker over its applicable engines.

        ``available[ticker]`` optionally restricts which engines apply to a
        ticker (used to exclude gex/insider where there is no datum). If a
        conditional engine is absent from ``available[ticker]`` it is
        dropped for that ticker rather than imputed neutral.
        """
        evidences = list(evidences)
        global_ic = {
            ev.engine: ev.global_ic(self.prior_strength) for ev in evidences
        }
        shrunk: dict[str, dict[EngineName, float]] = {}
        weights: dict[str, dict[EngineName, float]] = {}

        for ticker in tickers:
            per_engine: dict[EngineName, float] = {}
            for ev in evidences:
                if not self._applies(ev.engine, ticker, available):
                    continue
                per_engine[ev.engine] = ev.asset_ic(
                    ticker, global_ic[ev.engine], self.asset_shrinkage
                )
            shrunk[ticker] = per_engine
            weights[ticker] = self._normalize(per_engine)

        return WeightResult(
            weights=weights, shrunk_ic=shrunk, global_ic=global_ic
        )

    @staticmethod
    def _applies(
        engine: EngineName,
        ticker: str,
        available: Mapping[str, set[EngineName]] | None,
    ) -> bool:
        if engine not in CONDITIONAL_ENGINES:
            return True
        if available is None:
            return True
        return engine in available.get(ticker, set())

    @staticmethod
    def _normalize(
        per_engine: Mapping[EngineName, float],
    ) -> dict[EngineName, float]:
        raw = {e: max(0.0, ic) for e, ic in per_engine.items()}
        total = sum(raw.values())
        if total <= 0:
            # Ningún motor con IC positivo para este activo: sin señal
            # fiable. Pesos cero -> el score combinado será 0 (neutral).
            return {e: 0.0 for e in per_engine}
        return {e: w / total for e, w in raw.items()}
