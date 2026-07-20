"""Smoke test en vivo del motor GEX (Fase 3.6). Requiere red.

    python scripts/score_gex_subset.py

Calcula el perfil GEX completo (walls, gamma flip, balance) para el
subconjunto GEX con datos reales de yfinance. Los niveles impresos son
los que el spec 2.1.6 (validación nivel 3) pide comparar contra alguna
herramienta pública de gamma exposure; el signo del régimen y los strikes
clave deben ser consistentes. El motor es live-only (Enmienda v1.2).
"""

import sys
from datetime import date

import pandas as pd

from quantbot.data.universe import GEX_SUBSET, OPTIONS_VALIDATION_REFERENCE
from quantbot.engines.gex import MAX_EXPIRATION_DAYS, GexEngine

MAX_EXPIRATIONS = 5


def fetch_chains(ticker: str, as_of: date):
    import yfinance as yf

    yf_ticker = yf.Ticker(ticker)
    history = yf_ticker.history(period="5d", interval="1d", auto_adjust=False)
    if history.empty:
        raise RuntimeError(f"{ticker}: sin histórico reciente para el spot")
    spot = float(history["Close"].iloc[-1])
    chains: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for expiration in yf_ticker.options:
        days = (date.fromisoformat(expiration) - as_of).days
        if days < 0 or days > MAX_EXPIRATION_DAYS:
            continue
        chain = yf_ticker.option_chain(expiration)
        chains[expiration] = (chain.calls, chain.puts)
        if len(chains) >= MAX_EXPIRATIONS:
            break
    return spot, chains


def main() -> int:
    as_of = date.today()
    engine = GexEngine()
    for ticker in OPTIONS_VALIDATION_REFERENCE + GEX_SUBSET:
        try:
            spot, chains = fetch_chains(ticker, as_of)
            result, profile = engine.score_ticker(ticker, spot, chains, as_of)
            print(f"[OK] {ticker:<6} score {result.score:+.2f}")
            print(f"     {result.justification}")
        except Exception as exc:  # noqa: BLE001 - informe: registra y sigue
            print(f"[FALLA] {ticker}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
