"""Cross-asset correlation matrix (Capa 2.2, para evitar sobreexposición a
un mismo factor de riesgo). Alimenta el optimizador de cartera (Fase 6).
"""

import numpy as np
import pandas as pd


def correlation_matrix(
    closes: pd.DataFrame, *, min_overlap: int = 60
) -> pd.DataFrame:
    """Pearson correlation of daily log returns between tickers.

    ``closes``: wide frame (index dates, columns tickers). Pairs with fewer
    than ``min_overlap`` common observations are set to NaN (not enough
    data to trust the estimate) rather than silently computed on a handful
    of points.
    """
    if closes.shape[1] < 2:
        raise ValueError("se necesitan al menos 2 tickers para correlacionar")
    log_returns = np.log(closes / closes.shift(1))
    correlation = log_returns.corr(min_periods=min_overlap)
    return correlation


def factor_exposure(
    correlation: pd.DataFrame, threshold: float = 0.7
) -> dict[str, list[str]]:
    """Grupos de activos altamente correlacionados (|corr| >= threshold).

    Devuelve, por ticker, la lista de otros tickers con los que comparte
    factor de riesgo por encima del umbral. El optimizador usa esto para
    penalizar carteras concentradas en un mismo cluster.
    """
    groups: dict[str, list[str]] = {}
    tickers = list(correlation.columns)
    for ticker in tickers:
        peers = []
        for other in tickers:
            if other == ticker:
                continue
            value = correlation.loc[ticker, other]
            if pd.notna(value) and abs(value) >= threshold:
                peers.append(other)
        groups[ticker] = sorted(peers)
    return groups
