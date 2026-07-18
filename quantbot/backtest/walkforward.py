"""Walk-forward evaluation of one engine's predictive power.

Method (no fitting anywhere, so every observation is out-of-sample in the
statistical sense; the dev/holdout split additionally guards against the
DESIGN of the engine having been influenced by recent history):

- On each evaluation date t (spaced ``horizon`` sessions apart so forward
  returns do not overlap), score every ticker using ONLY data up to t.
- Forward return = adj_close[t + horizon] / adj_close[t] - 1.
- IC (information coefficient) = cross-sectional Spearman correlation
  between scores and forward returns on each date.
- Long-short spread = mean forward return of the top tercile of scores
  minus the bottom tercile (economic magnitude of the signal).
- t-stat of the mean IC over non-overlapping dates measures significance.
"""

from collections.abc import Callable, Mapping
from datetime import date
from math import sqrt

import pandas as pd
from pydantic import BaseModel, ConfigDict

MIN_CROSS_SECTION = 15  # tickers with score+return needed to compute an IC


class PeriodStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    n_dates: int
    mean_ic: float
    std_ic: float
    t_stat: float
    pct_ic_positive: float
    mean_ls_spread: float  # per-period (horizon) tercile long-short return


class WalkForwardReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    engine: str
    horizon_days: int
    development: PeriodStats
    holdout: PeriodStats


def spearman_ic(
    scores: Mapping[str, float], forward_returns: Mapping[str, float]
) -> float | None:
    """Cross-sectional rank correlation; None if the section is too small."""
    common = sorted(set(scores) & set(forward_returns))
    if len(common) < MIN_CROSS_SECTION:
        return None
    s = pd.Series({t: scores[t] for t in common})
    r = pd.Series({t: forward_returns[t] for t in common})
    if s.nunique() < 2 or r.nunique() < 2:
        return None
    # Spearman = Pearson sobre rangos (con empates promediados); evita la
    # dependencia de scipy que exigiría pandas con method="spearman".
    return float(s.rank().corr(r.rank(), method="pearson"))


def tercile_spread(
    scores: Mapping[str, float], forward_returns: Mapping[str, float]
) -> float | None:
    common = sorted(set(scores) & set(forward_returns))
    if len(common) < MIN_CROSS_SECTION:
        return None
    ranked = sorted(common, key=lambda t: scores[t])
    third = len(ranked) // 3
    if third == 0:
        return None
    bottom = ranked[:third]
    top = ranked[-third:]
    top_mean = sum(forward_returns[t] for t in top) / len(top)
    bottom_mean = sum(forward_returns[t] for t in bottom) / len(bottom)
    return top_mean - bottom_mean


def evaluate_engine(
    adj_closes: pd.DataFrame,
    score_fn: Callable[[str, list[float]], float],
    *,
    horizon: int,
    min_history: int,
) -> pd.DataFrame:
    """Evaluate ``score_fn`` over non-overlapping horizons.

    ``adj_closes``: wide frame (index: dates, columns: tickers), NaN where a
    ticker has no data. ``score_fn(ticker, closes_up_to_t)`` returns a score
    or raises (a raising ticker is simply excluded on that date).

    Returns a frame indexed by evaluation date with columns ``ic`` and
    ``ls_spread`` (rows where the cross-section was too small are dropped).
    """
    rows: list[dict] = []
    dates = adj_closes.index
    for i in range(min_history, len(dates) - horizon, horizon):
        current = dates[i]
        scores: dict[str, float] = {}
        forwards: dict[str, float] = {}
        for ticker in adj_closes.columns:
            history = adj_closes[ticker].iloc[: i + 1].dropna()
            future_price = adj_closes[ticker].iloc[i + horizon]
            current_price = adj_closes[ticker].iloc[i]
            if pd.isna(future_price) or pd.isna(current_price):
                continue
            try:
                scores[ticker] = score_fn(ticker, history.tolist())
            except Exception:  # noqa: BLE001 - ticker sin datos suficientes
                continue
            forwards[ticker] = float(future_price / current_price - 1)
        ic = spearman_ic(scores, forwards)
        spread = tercile_spread(scores, forwards)
        if ic is not None and spread is not None:
            rows.append({"date": current, "ic": ic, "ls_spread": spread})
    if not rows:
        raise ValueError(
            "ninguna fecha de evaluación con sección cruzada suficiente"
        )
    return pd.DataFrame(rows).set_index("date")


def period_stats(label: str, results: pd.DataFrame) -> PeriodStats:
    if len(results) < 8:
        raise ValueError(
            f"{label}: solo {len(results)} fechas de evaluación; "
            "insuficiente para estadística"
        )
    ics = results["ic"]
    mean = float(ics.mean())
    std = float(ics.std(ddof=1))
    return PeriodStats(
        label=label,
        n_dates=len(results),
        mean_ic=mean,
        std_ic=std,
        t_stat=mean / (std / sqrt(len(results))) if std > 0 else 0.0,
        pct_ic_positive=float((ics > 0).mean()),
        mean_ls_spread=float(results["ls_spread"].mean()),
    )


def split_report(
    engine: str,
    results: pd.DataFrame,
    *,
    horizon: int,
    split_date: date,
) -> WalkForwardReport:
    timestamps = pd.to_datetime(results.index)
    cutoff = pd.Timestamp(split_date)
    if timestamps.tz is not None:
        cutoff = cutoff.tz_localize(timestamps.tz)
    development = results[timestamps < cutoff]
    holdout = results[timestamps >= cutoff]
    return WalkForwardReport(
        engine=engine,
        horizon_days=horizon,
        development=period_stats(f"desarrollo (< {split_date})", development),
        holdout=period_stats(f"holdout (>= {split_date})", holdout),
    )
