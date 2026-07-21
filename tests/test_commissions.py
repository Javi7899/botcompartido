import pytest

from quantbot.portfolio.commissions import (
    CommissionFilter,
    FilterMode,
    ibkr_commission,
)


def test_commission_minimum_dominates_small_orders() -> None:
    # 10 acciones × $0.005 = $0.05, pero el mínimo es $1
    assert ibkr_commission(10, 150.0) == 1.00


def test_commission_per_share_above_minimum() -> None:
    # 500 acciones × $0.005 = $2.50 > $1
    assert ibkr_commission(500, 150.0) == 2.50


def test_commission_one_percent_cap() -> None:
    # operación de $50: 1% = $0.50, por debajo del mínimo → cap aplica
    assert ibkr_commission(1, 50.0) == pytest.approx(0.50)


def test_commission_zero_shares() -> None:
    assert ibkr_commission(0, 100.0) == 0.0


def test_commission_bad_price_raises() -> None:
    with pytest.raises(ValueError):
        ibkr_commission(10, 0.0)


def make_filter(mode=FilterMode.INDIVIDUAL, **kw) -> CommissionFilter:
    return CommissionFilter(mode=mode, **kw)


def test_individual_executes_when_bar_cleared() -> None:
    f = make_filter()
    # comprar 20 acciones a $150 = $3000, edge 5%: beneficio $150
    # comisión = max($1, 20×0.005)=$1; 3x=$3; 150 >= 3 -> ejecuta
    d = f.evaluate(
        ticker="AAPL", current_shares=0, target_shares=20, price=150.0,
        expected_edge=0.05, portfolio_value=5000.0,
    )
    assert d.execute is True
    assert d.delta_shares == 20
    assert d.commission == 1.0


def test_individual_blocked_by_small_deviation() -> None:
    f = make_filter(deviation_threshold=0.10)  # umbral 10%
    d = f.evaluate(
        ticker="AAPL", current_shares=0, target_shares=1, price=150.0,
        expected_edge=0.05, portfolio_value=5000.0,
    )
    # $150 / $5000 = 3% < 10%
    assert d.execute is False
    assert "desviación" in d.reason


def test_individual_blocked_by_commission_rule() -> None:
    f = make_filter(deviation_threshold=0.0)
    # edge minúsculo: beneficio < 3x comisión
    d = f.evaluate(
        ticker="AAPL", current_shares=0, target_shares=10, price=150.0,
        expected_edge=0.0001, portfolio_value=5000.0,
    )
    assert d.execute is False
    assert "comisión" in d.reason


def test_no_change_not_executed() -> None:
    f = make_filter()
    d = f.evaluate(
        ticker="AAPL", current_shares=10, target_shares=10, price=150.0,
        expected_edge=0.05, portfolio_value=5000.0,
    )
    assert d.execute is False
    assert d.delta_shares == 0


def test_aggregate_executes_small_adjustments_together() -> None:
    f = make_filter(FilterMode.AGGREGATE, deviation_threshold=0.05)
    # tres ajustes individualmente pequeños pero con buen edge agregado
    decisions = [
        f.evaluate(ticker=t, current_shares=0, target_shares=5, price=100.0,
                   expected_edge=0.05, portfolio_value=5000.0)
        for t in ("A", "B", "C")
    ]
    # en modo agregado, evaluate deja execute=False; apply_aggregate decide
    assert all(d.execute is False for d in decisions)
    final = f.apply_aggregate(decisions)
    # 3 × $500 = $1500 de turnover = 30% > 5%; beneficio 3×$25=$75 vs 3×$1=$3
    assert all(d.execute for d in final)


def test_aggregate_blocks_when_below_bar() -> None:
    f = make_filter(FilterMode.AGGREGATE, deviation_threshold=0.5)
    decisions = [
        f.evaluate(ticker="A", current_shares=0, target_shares=1, price=100.0,
                   expected_edge=0.001, portfolio_value=5000.0)
    ]
    final = f.apply_aggregate(decisions)
    assert all(d.execute is False for d in final)


def test_apply_aggregate_wrong_mode_raises() -> None:
    f = make_filter(FilterMode.INDIVIDUAL)
    with pytest.raises(ValueError, match="AGGREGATE"):
        f.apply_aggregate([])
