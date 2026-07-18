"""Smoke test en vivo del motor Fundamental (Fase 3.2). Requiere red.

    python scripts/score_fundamental_universe.py

Descarga los fundamentales del universo desde yfinance, calcula el score
transversal y lo imprime. Valida que los campos que el motor necesita
existen hoy en la fuente (el motor es live-only: sin backtest, ver
docs/FUENTES_DATOS.md).
"""

import sys

from quantbot.data.universe import UNIVERSE
from quantbot.engines.fundamental import (
    FundamentalEngine,
    fetch_universe_fundamentals,
)


def main() -> int:
    print(f"Descargando fundamentales de {len(UNIVERSE)} tickers...")
    metrics = fetch_universe_fundamentals(UNIVERSE)
    results, skipped = FundamentalEngine().score_universe(metrics)

    print(f"\nScores ({len(results)} tickers, orden descendente):")
    for result in sorted(results, key=lambda r: r.score, reverse=True):
        print(f"  {result.ticker:<6} {result.score:+.2f}  {result.justification}")
    if skipped:
        print(f"\nExcluidos ({len(skipped)}):")
        for ticker, reason in skipped.items():
            print(f"  {ticker}: {reason}")
    print(
        f"\nCobertura: {len(results)}/{len(UNIVERSE)} tickers con score."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
