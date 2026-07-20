import pytest

from quantbot.db.models import EngineName
from quantbot.meta.combine import combine_scores

TECH = EngineName.TECHNICAL
FUND = EngineName.FUNDAMENTAL
GEX = EngineName.GEX


def test_weighted_sum() -> None:
    result = combine_scores(
        "AAPL",
        engine_scores={TECH: 0.8, FUND: -0.4},
        engine_weights={TECH: 0.75, FUND: 0.25},
    )
    assert result.score == pytest.approx(0.75 * 0.8 + 0.25 * -0.4)
    assert result.engines_used == 2


def test_zero_weight_engine_excluded() -> None:
    result = combine_scores(
        "AAPL",
        engine_scores={TECH: 0.8, FUND: 0.9},
        engine_weights={TECH: 1.0, FUND: 0.0},
    )
    assert result.engines_used == 1
    assert result.score == pytest.approx(0.8)


def test_missing_score_engine_skipped() -> None:
    result = combine_scores(
        "AAPL",
        engine_scores={TECH: 0.5},  # sin GEX
        engine_weights={TECH: 0.5, GEX: 0.5},
    )
    assert result.engines_used == 1
    assert GEX not in result.contributions


def test_score_clamped() -> None:
    result = combine_scores(
        "AAPL",
        engine_scores={TECH: 1.0, FUND: 1.0},
        engine_weights={TECH: 0.8, FUND: 0.8},  # suma > 1 a propósito
    )
    assert result.score == 1.0


def test_out_of_range_score_raises() -> None:
    with pytest.raises(ValueError, match="fuera de rango"):
        combine_scores("AAPL", {TECH: 1.5}, {TECH: 1.0})


def test_empty_gives_zero() -> None:
    result = combine_scores("AAPL", {}, {})
    assert result.score == 0.0
    assert result.engines_used == 0
