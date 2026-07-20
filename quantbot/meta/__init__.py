"""Meta-model layer (Capa 2.2): hierarchical bayesian weighting and
cross-asset correlations. Built in Fase 4 on the surviving engines."""

from quantbot.meta.bayesian import (
    EngineEvidence,
    HierarchicalWeighter,
    Observation,
    WeightResult,
    information_coefficient,
    shrink,
)
from quantbot.meta.combine import CombinedScore, combine_scores
from quantbot.meta.correlations import correlation_matrix, factor_exposure

__all__ = [
    "CombinedScore",
    "EngineEvidence",
    "HierarchicalWeighter",
    "Observation",
    "WeightResult",
    "combine_scores",
    "correlation_matrix",
    "factor_exposure",
    "information_coefficient",
    "shrink",
]
