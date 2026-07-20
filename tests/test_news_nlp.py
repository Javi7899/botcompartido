from datetime import datetime, timedelta, timezone

import pytest

from quantbot.data.news import NewsItemRecord
from quantbot.db.models import EngineName
from quantbot.engines.news_nlp import NewsEngine, headline_sentiment

ENGINE = NewsEngine()
AS_OF = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc)


def item(title: str, hours_ago: float = 2.0) -> NewsItemRecord:
    return NewsItemRecord(
        ticker="AAPL",
        source="yahoo_ticker_rss",
        title=title,
        link=f"https://x.test/{abs(hash(title))}",
        published_at=AS_OF - timedelta(hours=hours_ago),
    )


def test_headline_sentiment_polarity() -> None:
    assert headline_sentiment("Apple beats estimates, record profit") == 1.0
    assert headline_sentiment("Apple misses badly, shares plunge") == -1.0
    assert headline_sentiment("Apple beats but faces lawsuit") == pytest.approx(0.0)
    assert headline_sentiment("Apple announces new phone") is None


def test_positive_news_scores_positive() -> None:
    items = [
        item("Apple beats revenue estimates"),
        item("Analysts upgrade Apple on strong growth"),
    ]
    result = ENGINE.score_ticker("AAPL", items, AS_OF)
    assert result.engine == EngineName.MACRO_NEWS
    assert result.score > 0.5
    assert "2 titulares" in result.justification


def test_negative_news_scores_negative() -> None:
    items = [item("Apple hit by lawsuit and probe"), item("Shares plunge")]
    assert ENGINE.score_ticker("AAPL", items, AS_OF).score < -0.5


def test_recency_weighting_favors_fresh_news() -> None:
    fresh_bad = [item("Shares plunge on weak guidance", 1.0)]
    old_good = [item("Record profit and strong growth", 40.0)]
    result = ENGINE.score_ticker("AAPL", fresh_bad + old_good, AS_OF)
    assert result.score < 0  # lo fresco domina


def test_out_of_window_ignored() -> None:
    stale = [item("Record profit surge", 72.0)]
    result = ENGINE.score_ticker("AAPL", stale, AS_OF)
    assert result.score == 0.0
    assert "sin titulares" in result.justification


def test_future_dated_item_ignored() -> None:
    future = [item("Record profit", hours_ago=-3.0)]
    assert ENGINE.score_ticker("AAPL", future, AS_OF).score == 0.0


def test_neutral_headlines_counted_but_not_scored() -> None:
    items = [item("Apple announces event"), item("Apple beats estimates")]
    result = ENGINE.score_ticker("AAPL", items, AS_OF)
    assert result.score > 0
    assert "1 neutrales" in result.justification


def test_naive_as_of_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ENGINE.score_ticker("AAPL", [], datetime(2026, 7, 18, 15, 0))
