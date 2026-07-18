"""Feature engineering for the ML engine (spec 2.1.4) — T-1 only.

Every feature at date t is computed exclusively from data up to and
including t (the T-1 close when the pipeline runs on day T). The target
for training is the 21-session forward return, cross-sectionally demeaned
per date so the model learns RELATIVE performance (market-neutral), not
the market's direction.

All windows are FIXED; nothing here is tuned.
"""

import numpy as np
import pandas as pd

HORIZON = 21

FEATURE_COLUMNS = (
    "ret_5d",
    "ret_21d",
    "ret_63d",
    "mom_12_1",
    "vol_21d",
    "vol_63d",
    "dist_52w_high",
    "dist_52w_low",
    "sma200_ratio",
    "volume_ratio",
)


def build_feature_frames(
    closes: pd.DataFrame, volumes: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """Wide per-feature frames (index dates, columns tickers)."""
    if not closes.index.equals(volumes.index) or list(closes.columns) != list(
        volumes.columns
    ):
        raise ValueError("closes y volumes deben compartir índice y columnas")
    returns = closes.pct_change()
    volume_clean = volumes.where(volumes > 0)
    features = {
        "ret_5d": closes.pct_change(5),
        "ret_21d": closes.pct_change(21),
        "ret_63d": closes.pct_change(63),
        "mom_12_1": closes.shift(21) / closes.shift(252) - 1,
        "vol_21d": returns.rolling(21).std(),
        "vol_63d": returns.rolling(63).std(),
        "dist_52w_high": closes / closes.rolling(252).max() - 1,
        "dist_52w_low": closes / closes.rolling(252).min() - 1,
        "sma200_ratio": closes / closes.rolling(200).mean() - 1,
        "volume_ratio": np.log(
            volume_clean.rolling(5).mean() / volume_clean.rolling(63).mean()
        ),
    }
    assert set(features) == set(FEATURE_COLUMNS)
    return features


def demeaned_forward_returns(closes: pd.DataFrame) -> pd.DataFrame:
    """Forward HORIZON-session return, demeaned across tickers per date."""
    forward = closes.shift(-HORIZON) / closes - 1
    return forward.sub(forward.mean(axis=1), axis=0)


def stack_features(
    features: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Long format: MultiIndex (date, ticker) x feature columns, rows with
    any missing feature dropped."""
    stacked = pd.concat(
        {name: frame.stack() for name, frame in features.items()}, axis=1
    )
    return stacked[list(FEATURE_COLUMNS)].dropna()


def build_dataset(
    closes: pd.DataFrame, volumes: pd.DataFrame
) -> tuple[pd.DataFrame, pd.Series]:
    """(X, y) aligned on (date, ticker); y is the demeaned forward return.

    Rows without a complete forward window (the last HORIZON dates) are
    NOT in y — callers must never train on them. X keeps them, because
    prediction at the live edge needs features without a target.
    """
    X = stack_features(build_feature_frames(closes, volumes))
    y = demeaned_forward_returns(closes).stack().dropna()
    y = y.loc[y.index.intersection(X.index)]
    return X, y
