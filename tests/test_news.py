import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from quantbot.data.news import NewsItemRecord, parse_entries, store_news
from quantbot.db.models import NewsArticle


def entry(title: str, link: str, published: str | None) -> dict:
    parsed = (
        time.strptime(published, "%Y-%m-%dT%H:%M:%S") if published else None
    )
    return {"title": title, "link": link, "published_parsed": parsed}


def test_parse_entries_ok() -> None:
    records, dropped = parse_entries(
        [entry("Apple sube", "https://x.test/1", "2026-07-17T14:30:00")],
        ticker="AAPL",
        source="yahoo_ticker_rss",
    )
    assert dropped == 0
    assert records[0].published_at == datetime(
        2026, 7, 17, 14, 30, tzinfo=timezone.utc
    )
    assert records[0].published_iso() == "2026-07-17T14:30:00+00:00"


def test_entries_without_timestamp_dropped() -> None:
    records, dropped = parse_entries(
        [
            entry("con fecha", "https://x.test/1", "2026-07-17T14:30:00"),
            entry("sin fecha", "https://x.test/2", None),
            {"title": "sin link", "published_parsed": None},
        ],
        ticker=None,
        source="cnbc_top_news",
    )
    assert len(records) == 1
    assert dropped == 2


def item(link: str, ticker: str | None = "AAPL") -> NewsItemRecord:
    return NewsItemRecord(
        ticker=ticker,
        source="yahoo_ticker_rss",
        title="titular",
        link=link,
        published_at=datetime(2026, 7, 17, 14, 30, tzinfo=timezone.utc),
    )


def test_store_news_dedupes_by_ticker_and_link(db_session: Session) -> None:
    assert store_news(db_session, [item("https://x.test/1")]) == 1
    assert store_news(db_session, [item("https://x.test/1")]) == 0
    # misma noticia asociada a otro ticker: fila nueva, es legítimo
    assert store_news(db_session, [item("https://x.test/1", ticker="MSFT")]) == 1


def test_news_archive_is_append_only(db_session: Session) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    store_news(db_session, [item("https://x.test/1")])
    row = db_session.execute(select(NewsArticle)).scalar_one()
    row.title = "titular reescrito"
    with pytest.raises(IntegrityError, match="append-only"):
        db_session.commit()
    db_session.rollback()
