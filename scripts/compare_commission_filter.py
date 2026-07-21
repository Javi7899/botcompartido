"""Compara las dos variantes del Filtro de Comisiones (gate de Fase 6).

    python scripts/compare_commission_filter.py

El spec (sección 3) exige decidir explícitamente el NIVEL DE APLICACIÓN del
filtro —por posición individual vs. sobre el rebalanceo agregado— tras
compararlos, no dejarlo implícito. Este script simula un año de
rebalanceos mensuales sobre precios reales del universo y mide, para cada
variante: órdenes generadas, comisiones totales y rotación.

La simulación NO es un backtest de rentabilidad (los motores de precio ya
fallaron su gate). Su único objetivo es dimensionar el coste y la
frecuencia de operación de cada variante con el capital real de 5.000 USD.
Requiere red.
"""

import sys
from datetime import date

import numpy as np
import pandas as pd

from quantbot.backtest.runner import HORIZON, download_universe_closes
from quantbot.data.universe import UNIVERSE
from quantbot.portfolio.black_litterman import black_litterman_weights
from quantbot.portfolio.commissions import CommissionFilter, FilterMode
from quantbot.portfolio.kelly import fractional_kelly_scale
from quantbot.portfolio.sizing import round_to_shares

CAPITAL = 5000.0
START = "2024-01-01"
EXPECTED_EDGE = 0.01  # 1% de mejora esperada por ajuste (supuesto explícito)


def simulate(closes: pd.DataFrame, mode: FilterMode) -> dict:
    """Rebalanceo mensual con la variante ``mode`` del filtro."""
    filtro = CommissionFilter(mode=mode)
    holdings: dict[str, int] = {}
    orders = 0
    commissions = 0.0
    turnover = 0.0
    rebalances = 0

    dates = closes.index
    returns = np.log(closes / closes.shift(1))
    for i in range(252, len(dates) - 1, HORIZON):
        window = returns.iloc[i - 252 : i + 1].dropna(axis=1, how="any")
        if window.shape[1] < 10:
            continue
        tickers = list(window.columns)
        cov = window.cov().to_numpy() * 252  # anualizada
        prices = {t: float(closes[t].iloc[i]) for t in tickers}
        # Scores sintéticos deterministas (momentum 3m centrado): el objetivo
        # es la mecánica de coste, no la señal.
        raw = np.array(
            [float(closes[t].iloc[i] / closes[t].iloc[i - 63] - 1) for t in tickers]
        )
        scores = np.clip((raw - raw.mean()) / (raw.std() or 1.0) / 2.0, -1, 1)
        market = np.full(len(tickers), 1.0 / len(tickers))

        weights = black_litterman_weights(cov, market, scores)
        if weights.sum() <= 0:
            continue
        exposure = fractional_kelly_scale(0.04, float(np.mean(np.diag(cov))))
        targets = round_to_shares(
            dict(zip(tickers, weights)), prices, CAPITAL, exposure=exposure
        )

        portfolio_value = CAPITAL
        decisions = []
        target_map = {p.ticker: p.shares for p in targets if p.investable}
        for ticker in set(list(holdings) + list(target_map)):
            price = prices.get(ticker)
            if price is None:
                continue
            decisions.append(
                filtro.evaluate(
                    ticker=ticker,
                    current_shares=holdings.get(ticker, 0),
                    target_shares=target_map.get(ticker, 0),
                    price=price,
                    expected_edge=EXPECTED_EDGE,
                    portfolio_value=portfolio_value,
                )
            )
        if mode == FilterMode.AGGREGATE:
            decisions = filtro.apply_aggregate(decisions)

        rebalances += 1
        for d in decisions:
            if not d.execute:
                continue
            orders += 1
            commissions += d.commission
            turnover += abs(d.delta_shares) * d.price
            holdings[d.ticker] = d.target_shares
        holdings = {t: s for t, s in holdings.items() if s > 0}

    return {
        "mode": mode.value,
        "rebalances": rebalances,
        "orders": orders,
        "commissions": commissions,
        "turnover": turnover,
        "commission_pct_capital": commissions / CAPITAL,
    }


def main() -> int:
    closes = download_universe_closes(START)
    print(
        f"Universo {len(UNIVERSE)} tickers, {len(closes)} sesiones "
        f"({closes.index[0].date()} -> {closes.index[-1].date()})\n"
    )
    rows = [simulate(closes, mode) for mode in FilterMode]
    header = (
        f"{'variante':<12} {'rebal.':>7} {'órdenes':>8} {'comisiones':>11} "
        f"{'turnover':>10} {'com/capital':>12}"
    )
    print(header)
    for r in rows:
        print(
            f"{r['mode']:<12} {r['rebalances']:>7} {r['orders']:>8} "
            f"{r['commissions']:>10.2f}$ {r['turnover']:>9.0f}$ "
            f"{r['commission_pct_capital']:>11.2%}"
        )
    print(
        "\nDecisión de Fase 6: ver docs/FASE6_CARTERA.md — se compara coste "
        "y frecuencia, no rentabilidad."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
