from quantbot.data.universe import (
    BENCHMARK,
    GEX_SUBSET,
    OPTIONS_VALIDATION_REFERENCE,
    UNIVERSE,
    UNIVERSE_FREEZE_DATE,
)


def test_universe_size_within_spec() -> None:
    assert 30 <= len(UNIVERSE) <= 40


def test_no_duplicates_and_sorted() -> None:
    assert len(set(UNIVERSE)) == len(UNIVERSE)
    assert list(UNIVERSE) == sorted(UNIVERSE)


def test_gex_subset_within_spec() -> None:
    assert 5 <= len(GEX_SUBSET) <= 10
    assert set(GEX_SUBSET) <= set(UNIVERSE)


def test_benchmark_not_in_universe() -> None:
    # SPY es benchmark y referencia de validación, nunca candidato a cartera.
    assert BENCHMARK == "SPY"
    assert BENCHMARK not in UNIVERSE
    assert BENCHMARK in OPTIONS_VALIDATION_REFERENCE


def test_freeze_date_is_iso() -> None:
    from datetime import date

    assert date.fromisoformat(UNIVERSE_FREEZE_DATE)
