import pytest

from quantbot.db.models import EngineName
from quantbot.meta.bayesian import (
    DEFAULT_PRIOR_IC,
    EngineEvidence,
    HierarchicalWeighter,
    information_coefficient,
    shrink,
)

TECH = EngineName.TECHNICAL
FUND = EngineName.FUNDAMENTAL
GEX = EngineName.GEX
INSIDER = EngineName.INSIDER


def monotonic_pairs(n: int, sign: float = 1.0) -> list[tuple[float, float]]:
    """Score i y retorno sign*i: IC = ±1 (correlación de rango perfecta)."""
    return [(float(i), sign * float(i)) for i in range(n)]


def test_information_coefficient_perfect() -> None:
    assert information_coefficient(monotonic_pairs(20)) == pytest.approx(1.0)
    assert information_coefficient(monotonic_pairs(20, -1.0)) == pytest.approx(-1.0)


def test_information_coefficient_too_few_is_none() -> None:
    assert information_coefficient(monotonic_pairs(5)) is None


def test_information_coefficient_no_variation_is_none() -> None:
    assert information_coefficient([(1.0, 5.0)] * 20) is None


def test_shrink_no_data_returns_prior() -> None:
    assert shrink(None, 0, 0.01, 100) == 0.01


def test_shrink_blends_toward_prior_with_few_obs() -> None:
    # 10 obs con IC 0.5, prior 0.0 con fuerza 100: casi todo prior
    blended = shrink(0.5, 10, 0.0, 100)
    assert blended == pytest.approx(0.5 * 10 / 110)


def test_shrink_converges_to_sample_with_many_obs() -> None:
    blended = shrink(0.5, 100_000, 0.0, 100)
    assert blended == pytest.approx(0.5, abs=1e-3)


def test_live_only_engine_sits_at_prior() -> None:
    """Un motor sin observaciones se queda en su prior conservador."""
    ev = EngineEvidence(engine=FUND, prior_ic=0.01)
    assert ev.global_ic(prior_strength=100) == 0.01


def test_backtested_engine_uses_evidence() -> None:
    ev = EngineEvidence(
        engine=TECH,
        prior_ic=0.0,
        global_pairs=monotonic_pairs(500),  # IC muestral 1.0
    )
    # 500 obs vs fuerza 100: se acerca a 1.0 pero no del todo
    global_ic = ev.global_ic(prior_strength=100)
    assert 0.75 < global_ic < 1.0


def test_per_asset_shrinks_toward_global() -> None:
    ev = EngineEvidence(
        engine=TECH,
        prior_ic=0.0,
        global_pairs=monotonic_pairs(1000),
        per_asset_pairs={
            "AAPL": monotonic_pairs(1000, -1.0),  # activo con IC contrario
            "NVDA": monotonic_pairs(15),  # poca evidencia
        },
    )
    global_ic = ev.global_ic(prior_strength=100)
    # AAPL con mucha evidencia contraria: su IC se aleja del global
    aapl = ev.asset_ic("AAPL", global_ic, asset_shrinkage=75)
    assert aapl < global_ic
    # NVDA con poca evidencia: se queda cerca del global
    nvda = ev.asset_ic("NVDA", global_ic, asset_shrinkage=75)
    assert abs(nvda - global_ic) < abs(aapl - global_ic)


def test_weighter_differentiates_by_asset() -> None:
    """El objetivo del spec: técnico pesa más donde predice mejor."""
    tech = EngineEvidence(
        engine=TECH,
        prior_ic=0.0,
        global_pairs=monotonic_pairs(400),
        per_asset_pairs={
            "AAPL": monotonic_pairs(400),  # técnico bueno en AAPL
            "NVDA": monotonic_pairs(400, -1.0),  # técnico malo en NVDA
        },
    )
    fund = EngineEvidence(
        engine=FUND,
        prior_ic=0.05,
        global_pairs=monotonic_pairs(400),
        per_asset_pairs={
            "AAPL": monotonic_pairs(400, -1.0),
            "NVDA": monotonic_pairs(400),
        },
    )
    result = HierarchicalWeighter().compute([tech, fund], ["AAPL", "NVDA"])
    # técnico domina en AAPL, fundamental en NVDA
    assert result.weights["AAPL"][TECH] > result.weights["AAPL"][FUND]
    assert result.weights["NVDA"][FUND] > result.weights["NVDA"][TECH]


def test_weights_normalized_per_asset() -> None:
    tech = EngineEvidence(engine=TECH, prior_ic=0.05)
    fund = EngineEvidence(engine=FUND, prior_ic=0.02)
    result = HierarchicalWeighter().compute([tech, fund], ["AAPL"])
    assert sum(result.weights["AAPL"].values()) == pytest.approx(1.0)


def test_negative_ic_engine_gets_zero_weight() -> None:
    good = EngineEvidence(engine=TECH, prior_ic=0.05)
    bad = EngineEvidence(
        engine=FUND, prior_ic=0.0, global_pairs=monotonic_pairs(500, -1.0)
    )
    result = HierarchicalWeighter().compute([good, bad], ["AAPL"])
    assert result.weights["AAPL"][FUND] == 0.0
    assert result.weights["AAPL"][TECH] == pytest.approx(1.0)


def test_conditional_engine_excluded_where_no_data() -> None:
    tech = EngineEvidence(engine=TECH, prior_ic=0.05)
    gex = EngineEvidence(engine=GEX, prior_ic=0.05)
    result = HierarchicalWeighter().compute(
        [tech, gex],
        ["AAPL", "KO"],
        available={"AAPL": {GEX}, "KO": set()},  # KO sin opciones líquidas
    )
    assert GEX in result.weights["AAPL"]
    assert GEX not in result.weights["KO"]
    assert result.weights["KO"][TECH] == pytest.approx(1.0)


def test_all_zero_ic_gives_zero_weights() -> None:
    flat = EngineEvidence(
        engine=TECH, prior_ic=0.0, global_pairs=monotonic_pairs(500, -1.0)
    )
    result = HierarchicalWeighter().compute([flat], ["AAPL"])
    assert result.weights["AAPL"][TECH] == 0.0
