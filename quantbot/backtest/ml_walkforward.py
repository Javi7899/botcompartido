"""Walk-forward evaluation for the ML engine (retraining + embargo).

Unlike the fixed-parameter engines, the ML model is FITTED, so leakage
discipline is critical:

- Retraining happens on an expanding window every ``retrain_every``
  sessions, using only samples whose 21-session forward window is fully
  realized at the evaluation date (embargo: sample date j is usable at
  evaluation index i only if j + horizon <= i).
- Predictions on each evaluation date use that date's features only.
- The evaluation grid, IC and spread definitions are identical to the
  other engines (quantbot/backtest/walkforward.py) so verdicts are
  comparable.
"""

from collections.abc import Callable

import pandas as pd

from quantbot.backtest.walkforward import spearman_ic, tercile_spread
from quantbot.engines.ml_features import FEATURE_COLUMNS, build_dataset


def evaluate_ml(
    closes: pd.DataFrame,
    volumes: pd.DataFrame,
    model_factory: Callable[[], object],
    *,
    horizon: int,
    min_history: int,
    retrain_every: int = 126,
    min_train_samples: int = 10_000,
) -> pd.DataFrame:
    """Returns the standard results frame (index date, columns ic/ls_spread).

    ``model_factory`` builds a fresh model exposing ``fit(X, y)`` and
    ``predict(X) -> array``; a fresh instance is created at each retrain
    so no state leaks across training windows.
    """
    X, y = build_dataset(closes, volumes)
    aligned = X.join(y.rename("target"), how="inner")
    dates = closes.index

    model = None
    last_train_index: int | None = None
    rows: list[dict] = []
    for i in range(min_history, len(dates) - horizon, horizon):
        if model is None or i - last_train_index >= retrain_every:
            train_end = dates[i - horizon]
            train = aligned[aligned.index.get_level_values(0) <= train_end]
            if len(train) >= min_train_samples:
                candidate = model_factory()
                candidate.fit(
                    train[list(FEATURE_COLUMNS)], train["target"]
                )
                model = candidate
                last_train_index = i
        if model is None:
            continue

        current_date = dates[i]
        try:
            features_today = X.loc[current_date]
        except KeyError:
            continue
        if isinstance(features_today, pd.Series) or len(features_today) < 2:
            continue
        predictions = pd.Series(
            model.predict(features_today[list(FEATURE_COLUMNS)]),
            index=features_today.index,
        )
        current_prices = closes.iloc[i]
        future_prices = closes.iloc[i + horizon]
        forwards = {
            ticker: float(future_prices[ticker] / current_prices[ticker] - 1)
            for ticker in features_today.index
            if pd.notna(future_prices[ticker])
            and pd.notna(current_prices[ticker])
        }
        scores = {t: float(predictions[t]) for t in forwards}
        ic = spearman_ic(scores, forwards)
        spread = tercile_spread(scores, forwards)
        if ic is not None and spread is not None:
            rows.append({"date": current_date, "ic": ic, "ls_spread": spread})

    if not rows:
        raise ValueError(
            "ninguna fecha de evaluación con modelo entrenado y sección "
            "cruzada suficiente"
        )
    return pd.DataFrame(rows).set_index("date")
