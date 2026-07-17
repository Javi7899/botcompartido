"""Timezone-aware clock helpers.

Spec section 1.1: the code must never assume a fixed Spain<->ET offset. All
market-time logic derives from ``zoneinfo`` with ``America/New_York`` so DST
transitions on both sides of the Atlantic are handled by the tz database.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from quantbot.config import MARKET_TIMEZONE

MARKET_TZ = ZoneInfo(MARKET_TIMEZONE)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_market() -> datetime:
    """Current time in the market timezone (America/New_York)."""
    return now_utc().astimezone(MARKET_TZ)


def iso_utc(dt: datetime) -> str:
    """ISO-8601 string in UTC. Rejects naive datetimes (noisy failure)."""
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime not allowed: {dt!r}")
    return dt.astimezone(timezone.utc).isoformat()


def iso_market(dt: datetime) -> str:
    """ISO-8601 string with the market (ET) UTC offset. Rejects naive datetimes."""
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime not allowed: {dt!r}")
    return dt.astimezone(MARKET_TZ).isoformat()
