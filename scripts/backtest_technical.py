"""Backtest walk-forward del motor Técnico (gate de Fase 3.1). Requiere red.

    python scripts/backtest_technical.py

Criterio de éxito PRE-REGISTRADO (antes de ver los resultados):
- El holdout empieza el 2022-01-01 (nunca usado para diseñar el motor).
- PASA si el IC medio del holdout es > 0 con t-stat >= 2.0.
- MARGINAL (se mantiene con peso bayesiano inicial bajo) si t-stat en [1.0, 2.0).
- FALLA (se simplifica o descarta el motor) si t-stat < 1.0.

El motor no tiene parámetros ajustados, así que todo el periodo es
out-of-sample en sentido estadístico; el corte 2022 protege además contra
el sesgo de diseño (el motor se diseñó conociendo la historia hasta hoy).
"""

import sys
from datetime import date

import pandas as pd

from quantbot.backtest.walkforward import WalkForwardReport, evaluate_engine, split_report
from quantbot.data.universe import UNIVERSE
from quantbot.engines.technical import MIN_BARS, TechnicalEngine

START = "2012-01-01"
HORIZON = 21
SPLIT_DATE = date(2022, 1, 1)
PASS_T_STAT = 2.0
MARGINAL_T_STAT = 1.0

REPORT_PATH = "docs/BACKTEST_MOTOR_TECNICO.md"


def download_universe_closes() -> pd.DataFrame:
    import yfinance as yf

    print(f"Descargando {len(UNIVERSE)} tickers desde {START}...")
    df = yf.download(
        tickers=list(UNIVERSE),
        start=START,
        interval="1d",
        auto_adjust=False,
        group_by="column",
        progress=False,
        threads=True,
    )
    adj = df["Adj Close"]
    missing = [t for t in UNIVERSE if t not in adj.columns or adj[t].dropna().empty]
    if missing:
        raise RuntimeError(f"tickers sin datos: {missing}")
    return adj[list(UNIVERSE)]


def verdict(t_stat: float) -> str:
    if t_stat >= PASS_T_STAT:
        return "PASA"
    if t_stat >= MARGINAL_T_STAT:
        return "MARGINAL"
    return "FALLA"


def render_markdown(report: WalkForwardReport, n_dates_total: int) -> str:
    dev, hold = report.development, report.holdout
    lines = [
        "# Backtest walk-forward — Motor Técnico (Fase 3.1)",
        "",
        f"Ejecutado el {date.today().isoformat()} sobre el universo congelado "
        f"({len(UNIVERSE)} tickers, datos yfinance desde {START}).",
        "",
        "## Metodología",
        "",
        f"- Horizonte de evaluación: {HORIZON} sesiones (no solapado).",
        "- Score calculado solo con datos hasta t (T-1 estricto); retorno "
        f"forward = adj_close[t+{HORIZON}]/adj_close[t] - 1.",
        "- IC = Spearman transversal score vs retorno forward por fecha.",
        "- Spread L-S = tercil superior menos tercil inferior por fecha.",
        "- Sin parámetros ajustados; corte de diseño out-of-sample: "
        f"{SPLIT_DATE.isoformat()}.",
        "",
        "## Criterio pre-registrado",
        "",
        f"- PASA: t-stat del IC medio en holdout >= {PASS_T_STAT}.",
        f"- MARGINAL: t-stat en [{MARGINAL_T_STAT}, {PASS_T_STAT}) — se "
        "mantiene con peso bayesiano inicial bajo.",
        f"- FALLA: t-stat < {MARGINAL_T_STAT} — se simplifica o descarta.",
        "",
        "## Resultados",
        "",
        "| Periodo | Fechas | IC medio | IC std | t-stat | % IC>0 | Spread L-S medio (21d) |",
        "|---|---|---|---|---|---|---|",
    ]
    for stats in (dev, hold):
        lines.append(
            f"| {stats.label} | {stats.n_dates} | {stats.mean_ic:+.4f} | "
            f"{stats.std_ic:.4f} | {stats.t_stat:+.2f} | "
            f"{stats.pct_ic_positive:.0%} | {stats.mean_ls_spread:+.4f} |"
        )
    result = verdict(hold.t_stat if hold.mean_ic > 0 else -abs(hold.t_stat))
    lines += [
        "",
        f"**Total de fechas de evaluación: {n_dates_total}.**",
        "",
        f"## Veredicto: {result}",
        "",
    ]
    if result == "PASA":
        lines.append(
            "El motor Técnico muestra capacidad predictiva out-of-sample "
            "significativa y queda aprobado para integrarse en la "
            "ponderación bayesiana (Fase 4) con la evidencia aquí registrada."
        )
    elif result == "MARGINAL":
        lines.append(
            "Evidencia débil: el motor se mantiene con peso bayesiano "
            "inicial bajo y su peso solo crecerá si el paper trading "
            "acumula evidencia adicional (coherente con spec 0.1/regla 3)."
        )
    else:
        lines.append(
            "Sin evidencia predictiva out-of-sample: según la regla 3 del "
            "spec, el motor debe simplificarse o descartarse antes de "
            "avanzar. NO integrar en Fase 4 tal cual."
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    closes = download_universe_closes()
    print(
        f"Datos: {len(closes)} sesiones, "
        f"{closes.notna().all(axis=1).sum()} completas para los 35 tickers"
    )
    engine = TechnicalEngine()

    def score_fn(ticker: str, history: list[float]) -> float:
        return engine.score(ticker, history).score

    results = evaluate_engine(
        closes, score_fn, horizon=HORIZON, min_history=MIN_BARS
    )
    report = split_report(
        "technical", results, horizon=HORIZON, split_date=SPLIT_DATE
    )
    markdown = render_markdown(report, len(results))
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    print(markdown)
    print(f"Informe guardado en {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
