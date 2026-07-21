import pytest

from quantbot.portfolio.sizing import round_to_shares


def test_basic_whole_share_rounding() -> None:
    positions = round_to_shares(
        {"AAPL": 0.5, "KO": 0.5},
        {"AAPL": 330.0, "KO": 60.0},
        capital=5000.0,
    )
    by_ticker = {p.ticker: p for p in positions}
    # $2500 asignado a cada uno
    assert by_ticker["AAPL"].shares == 7  # 2500//330 = 7
    assert by_ticker["KO"].shares == 41  # 2500//60 = 41
    assert all(p.investable for p in positions)


def test_non_investable_when_price_exceeds_allocation() -> None:
    # un activo carísimo con peso pequeño: no invertible
    positions = round_to_shares(
        {"EXPENSIVE": 0.05, "CHEAP": 0.95},
        {"EXPENSIVE": 900.0, "CHEAP": 50.0},
        capital=5000.0,
    )
    expensive = next(p for p in positions if p.ticker == "EXPENSIVE")
    assert not expensive.investable
    assert "no invertible" in expensive.note


def test_max_positions_limit() -> None:
    weights = {f"T{i}": 1.0 / 20 for i in range(20)}
    prices = {f"T{i}": 100.0 for i in range(20)}
    positions = round_to_shares(
        weights, prices, capital=50000.0, max_positions=15
    )
    assert len(positions) == 15


def test_min_position_size_excludes_tiny() -> None:
    positions = round_to_shares(
        {"BIG": 0.98, "TINY": 0.02},
        {"BIG": 100.0, "TINY": 100.0},
        capital=5000.0,
        min_position_usd=300.0,
    )
    tiny = next(p for p in positions if p.ticker == "TINY")
    # asignación ~$100 < mínimo $300
    assert not tiny.investable
    assert "mínimo" in tiny.note


def test_exposure_scales_deployment() -> None:
    full = round_to_shares(
        {"AAPL": 1.0}, {"AAPL": 100.0}, capital=5000.0, exposure=1.0
    )
    half = round_to_shares(
        {"AAPL": 1.0}, {"AAPL": 100.0}, capital=5000.0, exposure=0.5
    )
    assert full[0].shares == 50
    assert half[0].shares == 25


def test_zero_weight_tickers_ignored() -> None:
    positions = round_to_shares(
        {"AAPL": 1.0, "KO": 0.0},
        {"AAPL": 100.0, "KO": 50.0},
        capital=5000.0,
    )
    assert all(p.ticker != "KO" for p in positions)


def test_missing_price_marked_non_investable() -> None:
    positions = round_to_shares(
        {"AAPL": 0.5, "NOPRICE": 0.5},
        {"AAPL": 100.0},
        capital=5000.0,
    )
    noprice = next(p for p in positions if p.ticker == "NOPRICE")
    assert not noprice.investable


def test_position_count_derived_from_deployable_capital() -> None:
    """Con Kelly desplegando poco capital, el nº de posiciones se reduce en
    vez de trocear la asignación por debajo del precio de una acción."""
    weights = {f"T{i}": 1.0 / 15 for i in range(15)}
    prices = {f"T{i}": 200.0 for i in range(15)}
    positions = round_to_shares(
        weights, prices, capital=5000.0, exposure=0.23,
        max_positions=15, min_position_usd=300.0,
    )
    # desplegable = $1150 -> caben 3 posiciones de $300, no 15 de $77
    assert len(positions) == 3
    assert all(p.investable for p in positions)
    assert all(p.dollar_value >= 300.0 for p in positions)


def test_insufficient_deployable_capital_is_all_cash() -> None:
    positions = round_to_shares(
        {"AAPL": 1.0}, {"AAPL": 100.0}, capital=5000.0,
        exposure=0.02, min_position_usd=300.0,
    )
    # desplegable = $100 < mínimo de posición -> nada que comprar
    assert positions == []


def test_bad_capital_raises() -> None:
    with pytest.raises(ValueError):
        round_to_shares({"AAPL": 1.0}, {"AAPL": 100.0}, capital=0.0)


def test_bad_exposure_raises() -> None:
    with pytest.raises(ValueError):
        round_to_shares(
            {"AAPL": 1.0}, {"AAPL": 100.0}, capital=5000.0, exposure=1.5
        )
