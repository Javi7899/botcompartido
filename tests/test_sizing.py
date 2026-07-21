import pytest

from quantbot.portfolio.sizing import round_to_shares


def test_basic_whole_share_rounding() -> None:
    result = round_to_shares(
        {"AAPL": 0.5, "KO": 0.5},
        {"AAPL": 330.0, "KO": 60.0},
        capital=5000.0,
    )
    by_ticker = {p.ticker: p for p in result.positions}
    # $2500 asignado a cada uno
    assert by_ticker["AAPL"].shares == 7  # 2500//330 = 7
    assert by_ticker["KO"].shares == 41  # 2500//60 = 41
    assert all(p.investable for p in result.positions)
    assert result.excluded == []


def test_non_investable_ticker_excluded_with_reason() -> None:
    # un activo carísimo con peso pequeño: no cabe ni una acción
    result = round_to_shares(
        {"EXPENSIVE": 0.05, "CHEAP": 0.95},
        {"EXPENSIVE": 900.0, "CHEAP": 50.0},
        capital=5000.0,
    )
    assert [p.ticker for p in result.positions] == ["CHEAP"]
    expensive = next(p for p in result.excluded if p.ticker == "EXPENSIVE")
    assert not expensive.investable
    assert "no invertible" in expensive.note


def test_max_positions_limit() -> None:
    weights = {f"T{i}": 1.0 / 20 for i in range(20)}
    prices = {f"T{i}": 100.0 for i in range(20)}
    result = round_to_shares(
        weights, prices, capital=50000.0, max_positions=15
    )
    assert len(result.positions) == 15


def test_min_position_size_excludes_tiny() -> None:
    result = round_to_shares(
        {"BIG": 0.98, "TINY": 0.02},
        {"BIG": 100.0, "TINY": 100.0},
        capital=5000.0,
        min_position_usd=300.0,
    )
    assert [p.ticker for p in result.positions] == ["BIG"]
    tiny = next(p for p in result.excluded if p.ticker == "TINY")
    assert not tiny.investable


def test_exposure_scales_deployment() -> None:
    full = round_to_shares(
        {"AAPL": 1.0}, {"AAPL": 100.0}, capital=5000.0, exposure=1.0
    )
    half = round_to_shares(
        {"AAPL": 1.0}, {"AAPL": 100.0}, capital=5000.0, exposure=0.5
    )
    assert full.positions[0].shares == 50
    assert half.positions[0].shares == 25


def test_zero_weight_tickers_ignored() -> None:
    result = round_to_shares(
        {"AAPL": 1.0, "KO": 0.0},
        {"AAPL": 100.0, "KO": 50.0},
        capital=5000.0,
    )
    assert all(p.ticker != "KO" for p in result.positions)
    assert all(p.ticker != "KO" for p in result.excluded)


def test_missing_price_excluded() -> None:
    result = round_to_shares(
        {"AAPL": 0.5, "NOPRICE": 0.5},
        {"AAPL": 100.0},
        capital=5000.0,
    )
    assert [p.ticker for p in result.positions] == ["AAPL"]
    noprice = next(p for p in result.excluded if p.ticker == "NOPRICE")
    assert "sin precio" in noprice.note


def test_position_count_reduced_until_all_viable() -> None:
    """Con Kelly desplegando poco capital, el nº de posiciones se reduce en
    vez de trocear la asignación por debajo del mínimo tras redondear."""
    weights = {f"T{i}": 1.0 / 15 for i in range(15)}
    prices = {f"T{i}": 200.0 for i in range(15)}
    result = round_to_shares(
        weights, prices, capital=5000.0, exposure=0.23,
        max_positions=15, min_position_usd=300.0,
    )
    # desplegable = $1150: 3 posiciones darían $383 -> 1 acción de $200,
    # bajo el mínimo. Con 2 posiciones: $575 -> 2 acciones = $400. ✓
    assert len(result.positions) == 2
    assert all(p.investable for p in result.positions)
    assert all(p.dollar_value >= 300.0 for p in result.positions)
    assert result.invested_value == pytest.approx(800.0)


def test_insufficient_deployable_capital_is_all_cash() -> None:
    result = round_to_shares(
        {"AAPL": 1.0}, {"AAPL": 100.0}, capital=5000.0,
        exposure=0.02, min_position_usd=300.0,
    )
    # desplegable = $100 < mínimo de posición -> nada que comprar
    assert result.positions == []


def test_bad_capital_raises() -> None:
    with pytest.raises(ValueError):
        round_to_shares({"AAPL": 1.0}, {"AAPL": 100.0}, capital=0.0)


def test_bad_exposure_raises() -> None:
    with pytest.raises(ValueError):
        round_to_shares(
            {"AAPL": 1.0}, {"AAPL": 100.0}, capital=5000.0, exposure=1.5
        )
