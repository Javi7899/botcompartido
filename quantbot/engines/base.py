"""Common interface for the 7 signal engines (spec Capa 2.1).

Every engine returns a standardized score in [-1, 1] with a textual
justification and its data source — both are persisted per prediction
(spec 4.3) so the bayesian layer and the paper-trading evaluation can
audit each engine's reasoning after the fact.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from quantbot.db.models import EngineName


class InsufficientDataError(Exception):
    """The ticker lacks enough history for this engine. The pipeline decides
    whether to exclude the ticker or halt; the engine never guesses."""


class EngineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine: EngineName
    ticker: str
    score: float = Field(ge=-1.0, le=1.0)
    justification: str
    data_source: str


class SignalEngine(ABC):
    """An engine scores one ticker from its adjusted-close history (T-1)."""

    name: ClassVar[EngineName]

    @abstractmethod
    def score(self, ticker: str, adj_closes: Sequence[float]) -> EngineResult:
        """Compute the score using ONLY the provided history (last element
        is the T-1 official close; no intraday data, spec section 1)."""
