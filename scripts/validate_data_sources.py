"""Informe de validación de fuentes de datos (Fase 2). Requiere red.

Ejecuta contra las APIs reales y resume la calidad de cada fuente:
    python scripts/validate_data_sources.py

Este script implementa la validación de nivel 1 del spec (2.1.6 y Fase 2):
los totales de OI/IV impresos deben compararse manualmente contra CBOE o el
broker antes de dar por bueno cada ticker del subconjunto GEX.
"""

import sys
from datetime import date, timedelta

from quantbot.data import GEX_SUBSET
from quantbot.data.fred import DEFAULT_SERIES, fetch_series
from quantbot.data.news import MACRO_FEEDS, fetch_feed, fetch_ticker_news
from quantbot.data.ohlcv import fetch_daily_history, suspicious_moves
from quantbot.data.options import fetch_and_assess
from quantbot.data.universe import OPTIONS_VALIDATION_REFERENCE

OHLCV_SAMPLE = ("AAPL", "KO", "JPM")
NEWS_SAMPLE = ("AAPL", "NVDA")


def main() -> int:
    failures: list[str] = []
    today = date.today()

    print("=" * 70)
    print("VALIDACIÓN DE FUENTES DE DATOS — FASE 2")
    print("=" * 70)

    print("\n--- OHLCV (yfinance, 1 año) ---")
    for ticker in OHLCV_SAMPLE:
        try:
            bars = fetch_daily_history(ticker, today - timedelta(days=365), today)
            warnings = suspicious_moves(bars)
            print(
                f"[OK] {ticker}: {len(bars)} barras, "
                f"{bars[0].bar_date} -> {bars[-1].bar_date}, "
                f"último close {bars[-1].close_price:.2f}, "
                f"{len(warnings)} avisos"
            )
            for warning in warnings:
                print(f"     aviso: {warning}")
        except Exception as exc:  # noqa: BLE001 - informe: registra y sigue
            failures.append(f"OHLCV {ticker}: {exc}")
            print(f"[FALLA] {ticker}: {exc}")

    print("\n--- Macro (FRED, sin API key) ---")
    for series_id in DEFAULT_SERIES:
        try:
            observations = fetch_series(series_id)
            last = observations[-1]
            print(
                f"[OK] {series_id}: {len(observations)} observaciones, "
                f"última {last.obs_date} = {last.value}"
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"FRED {series_id}: {exc}")
            print(f"[FALLA] {series_id}: {exc}")

    print("\n--- Noticias (RSS, timestamps exactos) ---")
    for ticker in NEWS_SAMPLE:
        try:
            items = fetch_ticker_news(ticker)
            print(f"[OK] {ticker}: {len(items)} noticias con timestamp")
            for item in items[:3]:
                print(f"     {item.published_iso()}  {item.title[:70]}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"Noticias {ticker}: {exc}")
            print(f"[FALLA] {ticker}: {exc}")
    for source, url in MACRO_FEEDS.items():
        try:
            items = fetch_feed(url, ticker=None, source=source)
            print(f"[OK] {source}: {len(items)} noticias con timestamp")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"Feed {source}: {exc}")
            print(f"[FALLA] {source}: {exc}")

    print("\n--- Opciones (calidad para GEX; comparar OI/IV contra CBOE) ---")
    for ticker in OPTIONS_VALIDATION_REFERENCE + GEX_SUBSET:
        try:
            quality = fetch_and_assess(ticker)
            print(quality.summary())
            if not quality.passed:
                failures.append(f"Opciones {ticker}: {quality.issues}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"Opciones {ticker}: {exc}")
            print(f"[FALLA] {ticker}: {exc}")

    print("\n" + "=" * 70)
    if failures:
        print(f"RESULTADO: {len(failures)} problema(s) — revisar antes de Fase 3")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("RESULTADO: todas las fuentes validadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
