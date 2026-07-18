from datetime import date

import pytest

from quantbot.data.crosscheck import (
    OptionRef,
    atm_iv,
    compare_atm_iv,
    compare_closes,
    compare_oi,
    oi_by_expiration,
    parse_occ_symbol,
)
from quantbot.data.errors import DataSourceError


def test_parse_occ_symbol() -> None:
    expiration, is_call, strike = parse_occ_symbol("AAPL260918C00200000", "AAPL")
    assert expiration == date(2026, 9, 18)
    assert is_call is True
    assert strike == 200.0

    expiration, is_call, strike = parse_occ_symbol("SPY260731P00740500", "SPY")
    assert (expiration, is_call, strike) == (date(2026, 7, 31), False, 740.5)


def test_parse_occ_symbol_malformed() -> None:
    with pytest.raises(DataSourceError, match="malformado"):
        parse_occ_symbol("AAPL260918X00200000", "AAPL")
    with pytest.raises(DataSourceError, match="no empieza"):
        parse_occ_symbol("MSFT260918C00200000", "AAPL")


def ref(exp: str, strike: float, oi: int, iv: float | None) -> OptionRef:
    return OptionRef(
        expiration=date.fromisoformat(exp),
        is_call=True,
        strike=strike,
        open_interest=oi,
        iv=iv,
    )


def test_oi_by_expiration_and_atm_iv() -> None:
    options = [
        ref("2026-07-24", 96, 100, 0.30),
        ref("2026-07-24", 100, 200, 0.25),
        ref("2026-07-24", 130, 500, 0.90),  # lejos del spot: fuera del ATM
        ref("2026-07-31", 100, 50, 0.28),
    ]
    assert oi_by_expiration(options) == {
        date(2026, 7, 24): 800,
        date(2026, 7, 31): 50,
    }
    assert atm_iv(options, 100.0, date(2026, 7, 24)) == pytest.approx(0.275)


def test_compare_oi_within_tolerance() -> None:
    exps = {date(2026, 7, 24): 1000, date(2026, 7, 31): 500}
    similar = {date(2026, 7, 24): 1100, date(2026, 7, 31): 450}
    assert compare_oi("AAPL", exps, similar) == []


def test_compare_oi_deviation_flagged() -> None:
    yf = {date(2026, 7, 24): 1000, date(2026, 7, 31): 500}
    cboe = {date(2026, 7, 24): 3000, date(2026, 7, 31): 500}
    issues = compare_oi("AAPL", yf, cboe)
    assert len(issues) == 1
    assert "desviación" in issues[0]


def test_compare_oi_too_few_shared() -> None:
    issues = compare_oi("AAPL", {date(2026, 7, 24): 1}, {date(2026, 8, 21): 1})
    assert "compartidos" in issues[0]


def test_compare_atm_iv() -> None:
    assert compare_atm_iv("AAPL", 0.25, 0.27) == []
    assert compare_atm_iv("AAPL", 0.25, 0.50)
    assert compare_atm_iv("AAPL", None, 0.25)


def test_compare_closes() -> None:
    days = [date(2026, 7, d) for d in range(1, 21)]
    yf = {d: 100.0 for d in days}
    ok_ref = {d: 100.4 for d in days}
    assert compare_closes("AAPL", yf, ok_ref) == []

    bad_ref = dict(ok_ref)
    bad_ref[days[-1]] = 130.0
    issues = compare_closes("AAPL", yf, bad_ref)
    assert len(issues) == 1


def test_compare_closes_insufficient_overlap() -> None:
    issues = compare_closes("AAPL", {date(2026, 7, 1): 100.0}, {})
    assert "compartidas" in issues[0]


def test_parse_nasdaq_rows() -> None:
    from quantbot.data.crosscheck import parse_nasdaq_rows

    closes = parse_nasdaq_rows(
        [
            {"date": "07/17/2026", "close": "$333.74"},
            {"date": "07/16/2026", "close": "$1,333.26"},
        ],
        "AAPL",
    )
    assert closes == {
        date(2026, 7, 17): 333.74,
        date(2026, 7, 16): 1333.26,
    }


def test_parse_nasdaq_rows_malformed() -> None:
    from quantbot.data.crosscheck import parse_nasdaq_rows

    with pytest.raises(DataSourceError, match="no parseable"):
        parse_nasdaq_rows([{"date": "17-07-2026", "close": "$1"}], "AAPL")
    with pytest.raises(DataSourceError, match="sin filas"):
        parse_nasdaq_rows([], "AAPL")
