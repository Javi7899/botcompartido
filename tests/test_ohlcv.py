from datetime import date

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from quantbot.data.errors import DataQualityError, DataSourceError
from quantbot.data.ohlcv import (
    DailyBarRecord,
    parse_history_dataframe,
    store_bars,
    suspicious_moves,
    validate_bars,
)
from quantbot.db.models import DailyBar


def history_frame(rows: list[dict], dates: list[str]) -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [pd.Timestamp(d, tz="America/New_York") for d in dates]
    )
    return pd.DataFrame(rows, index=index)


ROW = {
    "Open": 100.0,
    "High": 105.0,
    "Low": 99.0,
    "Close": 104.0,
    "Adj Close": 103.5,
    "Volume": 1_000_000,
    "Dividends": 0.0,
    "Stock Splits": 0.0,
}


def make_bar(day: str, close: float = 104.0, split: float = 0.0) -> DailyBarRecord:
    return DailyBarRecord(
        ticker="AAPL",
        bar_date=date.fromisoformat(day),
        open_price=100.0,
        high_price=max(105.0, close),
        low_price=99.0,
        close_price=close,
        adj_close=close,
        volume=1_000_000,
        split_ratio=split,
    )


def test_parse_valid_frame() -> None:
    df = history_frame([ROW, ROW | {"Close": 101.0}], ["2026-07-15", "2026-07-16"])
    bars = parse_history_dataframe(df, "AAPL")
    assert len(bars) == 2
    assert bars[0].bar_date == date(2026, 7, 15)
    assert bars[1].close_price == 101.0
    assert bars[0].adj_close == 103.5


def test_empty_frame_raises() -> None:
    with pytest.raises(DataSourceError, match="vacío"):
        parse_history_dataframe(pd.DataFrame(), "AAPL")


def test_missing_column_raises() -> None:
    df = history_frame([{k: v for k, v in ROW.items() if k != "Adj Close"}],
                       ["2026-07-15"])
    with pytest.raises(DataSourceError, match="Adj Close"):
        parse_history_dataframe(df, "AAPL")


def test_nan_raises() -> None:
    df = history_frame([ROW | {"Close": float("nan")}], ["2026-07-15"])
    with pytest.raises(DataQualityError, match="NaN"):
        parse_history_dataframe(df, "AAPL")


def test_validate_duplicate_dates() -> None:
    bars = [make_bar("2026-07-15"), make_bar("2026-07-15")]
    with pytest.raises(DataQualityError, match="duplicada"):
        validate_bars(bars)


def test_validate_close_outside_range() -> None:
    bad = make_bar("2026-07-15").model_copy(update={"close_price": 200.0})
    with pytest.raises(DataQualityError, match="fuera del rango"):
        validate_bars([bad])


def test_suspicious_move_without_split_flagged() -> None:
    bars = [make_bar("2026-07-15", close=100.0), make_bar("2026-07-16", close=180.0)]
    warnings = suspicious_moves(bars)
    assert len(warnings) == 1
    assert "sin split" in warnings[0]


def test_move_with_split_not_flagged() -> None:
    bars = [
        make_bar("2026-07-15", close=100.0),
        make_bar("2026-07-16", close=50.0, split=2.0),
    ]
    assert suspicious_moves(bars) == []


def test_store_bars_idempotent(db_session: Session) -> None:
    bars = [make_bar("2026-07-15"), make_bar("2026-07-16")]
    assert store_bars(db_session, bars) == 2
    assert store_bars(db_session, bars) == 0
    stored = db_session.execute(select(DailyBar)).scalars().all()
    assert len(stored) == 2
    assert stored[0].source == "yfinance"


def test_store_bars_conflict_raises(db_session: Session) -> None:
    store_bars(db_session, [make_bar("2026-07-15")])
    revised = make_bar("2026-07-15").model_copy(update={"close_price": 101.0})
    with pytest.raises(DataQualityError, match="distintos"):
        store_bars(db_session, [revised])


def test_store_bars_tolerates_adj_close_drift(db_session: Session) -> None:
    """yfinance recalcula adj_close tras cada dividendo: no es conflicto."""
    store_bars(db_session, [make_bar("2026-07-15")])
    drifted = make_bar("2026-07-15").model_copy(update={"adj_close": 90.0})
    assert store_bars(db_session, [drifted]) == 0
