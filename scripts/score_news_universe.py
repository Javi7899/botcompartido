"""Smoke test en vivo del motor de Noticias (Fase 3.7). Requiere red.

    python scripts/score_news_universe.py

Descarga los feeds RSS por ticker de un subconjunto y calcula el score de
sentimiento con recencia. Live-only (spec 0.1).
"""

import sys

from quantbot.data.news import fetch_ticker_news
from quantbot.engines.news_nlp import NewsEngine
from quantbot.time_utils import now_utc

SMOKE_TICKERS = ("AAPL", "NVDA", "MSFT", "TSLA", "JPM", "PFE")


def main() -> int:
    as_of = now_utc()
    engine = NewsEngine()
    for ticker in SMOKE_TICKERS:
        try:
            items = fetch_ticker_news(ticker)
            result = engine.score_ticker(ticker, items, as_of)
            print(
                f"[OK] {ticker:<6} {result.score:+.2f}  "
                f"({len(items)} noticias descargadas)"
            )
            print(f"     {result.justification}")
        except Exception as exc:  # noqa: BLE001 - informe: registra y sigue
            print(f"[FALLA] {ticker}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
