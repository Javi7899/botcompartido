"""Deriva los pesos bayesianos jerárquicos iniciales de la Fase 4.

    python scripts/build_bayesian_weights.py

Construye la evidencia de cada motor integrable y calcula los pesos por
activo. En este punto (antes de Fase 8) solo el motor Técnico tiene
evidencia histórica (del walk-forward de Fase 3); los motores live-only
(Fundamental, Insider, GEX, Noticias) arrancan en su prior conservador.
Persiste los pesos globales y por activo en la tabla bayesian_weights e
imprime un resumen y la matriz de correlaciones del universo. Requiere red.
"""

import sys
from datetime import date

import pandas as pd

from quantbot.backtest.runner import (
    HORIZON,
    SPLIT_DATE,
    download_universe_closes,
)
from quantbot.config import load_config
from quantbot.data.universe import GEX_SUBSET, UNIVERSE
from quantbot.db import (
    BayesianWeight,
    EngineName,
    PipelineRun,
    create_db_engine,
    create_session_factory,
    init_db,
)
from quantbot.engines.technical import MIN_BARS, TechnicalEngine
from quantbot.meta.bayesian import (
    DEFAULT_PRIOR_IC,
    EngineEvidence,
    HierarchicalWeighter,
)
from quantbot.meta.correlations import correlation_matrix, factor_exposure
from quantbot.time_utils import iso_market, iso_utc, now_market, now_utc

# Priors conservadores por motor. El Técnico usa evidencia real; el resto
# arranca en un prior bajo (live-only, sube con paper trading — spec 0.1).
LIVE_ONLY_PRIOR = DEFAULT_PRIOR_IC


def build_technical_evidence(closes: pd.DataFrame) -> EngineEvidence:
    """Genera pares (score, retorno_forward) del motor Técnico en holdout
    (2022+), que es la evidencia out-of-sample honesta para el peso."""
    engine = TechnicalEngine()
    dates = closes.index
    cutoff = pd.Timestamp(SPLIT_DATE)
    if dates.tz is not None:
        cutoff = cutoff.tz_localize(dates.tz)

    global_pairs: list[tuple[float, float]] = []
    per_asset: dict[str, list[tuple[float, float]]] = {t: [] for t in UNIVERSE}
    for i in range(MIN_BARS, len(dates) - HORIZON, HORIZON):
        if dates[i] < cutoff:
            continue
        for ticker in UNIVERSE:
            history = closes[ticker].iloc[: i + 1].dropna()
            future = closes[ticker].iloc[i + HORIZON]
            current = closes[ticker].iloc[i]
            if pd.isna(future) or pd.isna(current) or len(history) < MIN_BARS:
                continue
            try:
                score = engine.score(ticker, history.tolist()).score
            except Exception:  # noqa: BLE001 - ticker sin datos: se omite
                continue
            forward = float(future / current - 1)
            global_pairs.append((score, forward))
            per_asset[ticker].append((score, forward))

    return EngineEvidence(
        engine=EngineName.TECHNICAL,
        prior_ic=0.0,  # sin prior: el peso lo determina la evidencia
        global_pairs=global_pairs,
        per_asset_pairs=per_asset,
    )


def persist(result, run_id: int, session) -> None:
    now_iso = iso_utc(now_utc())
    for engine, ic in result.global_ic.items():
        session.add(
            BayesianWeight(
                run_id=run_id,
                engine=engine.value,
                ticker=None,
                weight=max(0.0, ic),
                evidence_count=0,
                created_at_utc=now_iso,
            )
        )
    for ticker, engine_weights in result.weights.items():
        for engine, weight in engine_weights.items():
            session.add(
                BayesianWeight(
                    run_id=run_id,
                    engine=engine.value,
                    ticker=ticker,
                    weight=weight,
                    evidence_count=0,
                    created_at_utc=now_iso,
                )
            )
    session.commit()


def main() -> int:
    config = load_config()
    closes = download_universe_closes()

    print("Construyendo evidencia del motor Técnico (holdout 2022+)...")
    tech = build_technical_evidence(closes)

    evidences = [tech] + [
        EngineEvidence(engine=e, prior_ic=LIVE_ONLY_PRIOR)
        for e in (
            EngineName.FUNDAMENTAL,
            EngineName.INSIDER,
            EngineName.GEX,
            EngineName.MACRO_NEWS,
        )
    ]
    # GEX e Insider solo aplican a su subconjunto; Insider a todo el
    # universo (EDGAR cubre todos), GEX solo al subconjunto líquido.
    available = {
        t: (
            {EngineName.INSIDER}
            | ({EngineName.GEX} if t in GEX_SUBSET else set())
        )
        for t in UNIVERSE
    }

    weighter = HierarchicalWeighter()
    result = weighter.compute(evidences, UNIVERSE, available=available)

    print("\n=== IC global por motor (shrunk hacia prior) ===")
    for engine, ic in result.global_ic.items():
        print(f"  {engine.value:<14} IC={ic:+.4f}  peso_global={max(0, ic):.4f}")

    print("\n=== Pesos por activo (muestra) ===")
    for ticker in ("AAPL", "NVDA", "KO", "JPM"):
        parts = ", ".join(
            f"{e.value}={w:.2f}" for e, w in result.weights[ticker].items() if w > 0
        )
        print(f"  {ticker:<6} {parts}")

    print("\n=== Correlaciones (clusters de factor >= 0.7) ===")
    corr = correlation_matrix(closes.dropna())
    groups = factor_exposure(corr, threshold=0.7)
    for ticker, peers in sorted(groups.items()):
        if peers:
            print(f"  {ticker}: {', '.join(peers)}")

    # Persistencia
    db_engine = create_db_engine(config.db_path)
    init_db(db_engine)
    session_factory = create_session_factory(db_engine)
    with session_factory() as session:
        run = PipelineRun(
            started_at_utc=iso_utc(now_utc()),
            started_at_et=iso_market(now_market()),
            trading_date=date.today().isoformat(),
            environment=config.environment,
            finished_at_utc=iso_utc(now_utc()),
        )
        session.add(run)
        session.flush()
        persist(result, run.id, session)
        print(f"\nPesos persistidos en {config.db_path} (run {run.id}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
