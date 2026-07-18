from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from quantbot.data.errors import DataQualityError, DataSourceError
from quantbot.data.fred import (
    MacroObservationRecord,
    fetch_series,
    parse_fred_csv,
    store_observations,
)

CSV_OK = "DATE,DGS10\n2026-07-15,4.25\n2026-07-16,.\n2026-07-17,4.30\n"
CSV_NEW_HEADER = "observation_date,DGS10\n2026-07-17,4.30\n"


def test_parse_ok_skips_dots() -> None:
    obs = parse_fred_csv(CSV_OK, "DGS10")
    assert len(obs) == 2
    assert obs[0].obs_date == date(2026, 7, 15)
    assert obs[1].value == 4.30


def test_parse_skips_empty_values() -> None:
    # Variante real observada en la validación en vivo: FRED usa '' además
    # de '.' para observaciones sin valor.
    csv_empty = "DATE,DGS10\n1962-02-12,\n2026-07-17,4.30\n"
    obs = parse_fred_csv(csv_empty, "DGS10")
    assert len(obs) == 1
    assert obs[0].value == 4.30


def test_parse_accepts_new_header_variant() -> None:
    assert len(parse_fred_csv(CSV_NEW_HEADER, "DGS10")) == 1


def test_parse_empty_raises() -> None:
    with pytest.raises(DataSourceError, match="vacía"):
        parse_fred_csv("", "DGS10")


def test_parse_bad_header_raises() -> None:
    with pytest.raises(DataSourceError, match="cabecera"):
        parse_fred_csv("foo,bar,baz\n1,2,3\n", "DGS10")


def test_parse_bad_value_raises() -> None:
    with pytest.raises(DataSourceError, match="no parseable"):
        parse_fred_csv("DATE,DGS10\n2026-07-15,abc\n", "DGS10")


def test_parse_all_dots_raises() -> None:
    with pytest.raises(DataSourceError, match="ninguna observación"):
        parse_fred_csv("DATE,DGS10\n2026-07-15,.\n", "DGS10")


def test_fetch_http_error_raises() -> None:
    def fake_get(url, params, timeout):
        return SimpleNamespace(status_code=500, text="")

    with pytest.raises(DataSourceError, match="HTTP 500"):
        fetch_series("DGS10", http_get=fake_get)


def test_fetch_ok_with_fake_http() -> None:
    def fake_get(url, params, timeout):
        assert params == {"id": "DGS10"}
        return SimpleNamespace(status_code=200, text=CSV_OK)

    assert len(fetch_series("DGS10", http_get=fake_get)) == 2


def obs(day: str, value: float) -> MacroObservationRecord:
    return MacroObservationRecord(
        series_id="DGS10", obs_date=date.fromisoformat(day), value=value
    )


def test_store_idempotent(db_session: Session) -> None:
    observations = [obs("2026-07-15", 4.25), obs("2026-07-17", 4.30)]
    assert store_observations(db_session, observations) == 2
    assert store_observations(db_session, observations) == 0


def test_store_revision_raises(db_session: Session) -> None:
    store_observations(db_session, [obs("2026-07-15", 4.25)])
    with pytest.raises(DataQualityError, match="revisó"):
        store_observations(db_session, [obs("2026-07-15", 4.26)])
