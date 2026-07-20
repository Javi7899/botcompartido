"""Smoke test en vivo del motor Insider (Fase 3.5). Requiere red.

    python scripts/score_insider_universe.py

Descarga los Form 4 de los últimos 90 días vía EDGAR para un subconjunto
del universo (peticiones limitadas por cortesía con la SEC) y calcula el
score. El motor es live-only (Enmienda v1.2).
"""

import sys
from datetime import date, timedelta

from quantbot.data.edgar import fetch_cik_map, fetch_insider_transactions
from quantbot.engines.insider import LOOKBACK_DAYS, InsiderEngine

SMOKE_TICKERS = ("AAPL", "NVDA", "MSFT", "JPM", "XOM", "INTC")


def main() -> int:
    as_of = date.today()
    since = as_of - timedelta(days=LOOKBACK_DAYS)
    print("Descargando mapa de CIKs de la SEC...")
    cik_map = fetch_cik_map()
    engine = InsiderEngine()

    for ticker in SMOKE_TICKERS:
        cik10 = cik_map.get(ticker)
        if cik10 is None:
            print(f"[FALLA] {ticker}: sin CIK en el mapa de la SEC")
            continue
        try:
            transactions = fetch_insider_transactions(ticker, cik10, since)
            result = engine.score_ticker(ticker, transactions, as_of)
            print(
                f"[OK] {ticker:<6} {result.score:+.2f}  "
                f"({len(transactions)} transacciones descargadas)"
            )
            print(f"     {result.justification}")
        except Exception as exc:  # noqa: BLE001 - informe: registra y sigue
            print(f"[FALLA] {ticker}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
