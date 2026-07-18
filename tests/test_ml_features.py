import numpy as np
import pandas as pd
import pytest

from quantbot.engines.ml_features import (
    FEATURE_COLUMNS,
    HORIZON,
    build_dataset,
    build_feature_frames,
    demeaned_forward_returns,
    stack_features,
)

TICKERS = ["AAA", "BBB", "CCC"]


def make_data(n: int = 320, seed: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes = pd.DataFrame(
        {
            t: 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
            for t in TICKERS
        },
        index=dates,
    )
    volumes = pd.DataFrame(
        {t: rng.integers(1_000_000, 5_000_000, n).astype(float) for t in TICKERS},
        index=dates,
    )
    return closes, volumes


def test_known_feature_values_on_constant_growth() -> None:
    n = 320
    dates = pd.bdate_range("2024-01-02", periods=n)
    closes = pd.DataFrame(
        {t: [100.0 * 1.001**i for i in range(n)] for t in TICKERS}, index=dates
    )
    volumes = pd.DataFrame({t: [1e6] * n for t in TICKERS}, index=dates)
    features = build_feature_frames(closes, volumes)
    last = features["ret_5d"].iloc[-1]["AAA"]
    assert last == pytest.approx(1.001**5 - 1)
    assert features["vol_21d"].iloc[-1]["AAA"] == pytest.approx(0.0, abs=1e-9)
    assert features["volume_ratio"].iloc[-1]["AAA"] == pytest.approx(0.0)
    # crecimiento constante: el máximo de 52 semanas es el propio close
    assert features["dist_52w_high"].iloc[-1]["AAA"] == pytest.approx(0.0)


def test_features_are_causal_no_lookahead() -> None:
    closes, volumes = make_data()
    features_before = build_feature_frames(closes, volumes)
    tampered = closes.copy()
    tampered.iloc[-30:] *= 5.0  # reescribir el "futuro"
    features_after = build_feature_frames(tampered, volumes)
    checkpoint = closes.index[-40]  # anterior a la manipulación
    for name in FEATURE_COLUMNS:
        pd.testing.assert_series_equal(
            features_before[name].loc[checkpoint],
            features_after[name].loc[checkpoint],
        )


def test_demeaned_target_zero_mean_and_no_tail() -> None:
    closes, _ = make_data()
    target = demeaned_forward_returns(closes)
    row = target.iloc[100]
    assert row.mean() == pytest.approx(0.0, abs=1e-12)
    # las últimas HORIZON fechas no tienen ventana forward completa
    assert target.iloc[-HORIZON:].isna().all().all()


def test_stack_drops_incomplete_rows() -> None:
    closes, volumes = make_data()
    stacked = stack_features(build_feature_frames(closes, volumes))
    assert list(stacked.columns) == list(FEATURE_COLUMNS)
    assert not stacked.isna().any().any()
    # las primeras ~252 sesiones carecen de mom_12_1/dist_52w
    first_date = stacked.index.get_level_values(0).min()
    assert first_date >= closes.index[251]


def test_build_dataset_alignment() -> None:
    closes, volumes = make_data()
    X, y = build_dataset(closes, volumes)
    assert y.index.isin(X.index).all()
    # X conserva el borde vivo (features sin target todavía)
    assert X.index.get_level_values(0).max() == closes.index[-1]
    assert y.index.get_level_values(0).max() <= closes.index[-HORIZON - 1]


def test_mismatched_frames_raise() -> None:
    closes, volumes = make_data()
    with pytest.raises(ValueError, match="compartir"):
        build_feature_frames(closes, volumes.iloc[:-5])
