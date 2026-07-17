from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from quantbot.time_utils import iso_market, iso_utc, now_market, now_utc


def test_now_utc_is_aware_utc() -> None:
    now = now_utc()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_now_market_is_new_york() -> None:
    now = now_market()
    assert now.tzinfo is not None
    # EST (UTC-5) or EDT (UTC-4) depending on the date — never a fixed offset.
    assert now.utcoffset() in (timedelta(hours=-5), timedelta(hours=-4))


def test_iso_utc_normalizes_to_utc() -> None:
    dt = datetime(2026, 7, 17, 15, 30, tzinfo=ZoneInfo("Europe/Madrid"))
    assert iso_utc(dt) == "2026-07-17T13:30:00+00:00"


def test_iso_market_summer_and_winter_offsets_differ() -> None:
    summer = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    winter = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    assert iso_market(summer).endswith("-04:00")
    assert iso_market(winter).endswith("-05:00")


@pytest.mark.parametrize("func", [iso_utc, iso_market])
def test_naive_datetime_rejected(func) -> None:
    with pytest.raises(ValueError, match="naive"):
        func(datetime(2026, 7, 17, 12, 0))
