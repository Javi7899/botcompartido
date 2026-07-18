"""Shared walk-forward backtest runner for price-based engines.

Every engine backtest uses the SAME pre-registered protocol (so no engine
gets a friendlier yardstick than another):

- Universe: the frozen 35-ticker universe, yfinance Adj Close since 2012.
- Horizon 21 sessions, non-overlapping evaluation dates.
- Development < 2022-01-01 <= holdout.
- Verdict on holdout t-stat: PASA >= 2.0, MARGINAL [1.0, 2.0), FALLA < 1.0.
"""

from collections.abc import Callable
from datetime import date

import pandas as pd

from quantbot.backtest.walkforward import (
    WalkForwardReport,
    evaluate_engine,
    split_report,
)
from quantbot.data.universe import UNIVERSE

START = "2012-01-01"
HORIZON = 21
SPLIT_DATE = date(2022, 1, 1)
PASS_T_STAT = 2.0
MARGINAL_T_STAT = 1.0


def download_universe_closes(start: str = START) -> pd.DataFrame:
    import yfinance as yf

    print(f"Descargando {len(UNIVERSE)} tickers desde {start}...")
    df = yf.download(
        tickers=list(UNIVERSE),
        start=start,
        interval="1d",
        auto_adjust=False,
        group_by="column",
        progress=False,
        threads=True,
    )
    adj = df["Adj Close"]
    missing = [
        t for t in UNIVERSE if t not in adj.columns or adj[t].dropna().empty
    ]
    if missing:
        raise RuntimeError(f"tickers sin datos: {missing}")
    return adj[list(UNIVERSE)]


def development_only(closes: pd.DataFrame) -> pd.DataFrame:
    """Slice ending before the holdout — for simplification analyses."""
    cutoff = pd.Timestamp(SPLIT_DATE)
    if closes.index.tz is not None:
        cutoff = cutoff.tz_localize(closes.index.tz)
    return closes[closes.index < cutoff]


def verdict(holdout_mean_ic: float, holdout_t_stat: float) -> str:
    t = holdout_t_stat if holdout_mean_ic > 0 else -abs(holdout_t_stat)
    if t >= PASS_T_STAT:
        return "PASA"
    if t >= MARGINAL_T_STAT:
        return "MARGINAL"
    return "FALLA"


VERDICT_TEXT = {
    "PASA": (
        "El motor muestra capacidad predictiva out-of-sample significativa "
        "y queda aprobado para integrarse en la ponderación bayesiana "
        "(Fase 4) con la evidencia aquí registrada."
    ),
    "MARGINAL": (
        "Evidencia débil: el motor se mantiene con peso bayesiano inicial "
        "bajo y su peso solo crecerá si el paper trading acumula evidencia "
        "adicional (coherente con spec 0.1/regla 3)."
    ),
    "FALLA": (
        "Sin evidencia predictiva out-of-sample: según la regla 3 del spec, "
        "el motor debe simplificarse o descartarse antes de avanzar. "
        "NO integrar en Fase 4 tal cual."
    ),
}


def run_price_engine_backtest(
    *,
    engine_label: str,
    score_fn: Callable[[str, list[float]], float],
    min_history: int,
    report_title: str,
    report_path: str,
    design_notes: list[str] | None = None,
) -> tuple[WalkForwardReport, str]:
    """Run the standard backtest, write the markdown report, return both."""
    closes = download_universe_closes()
    results = evaluate_engine(
        closes, score_fn, horizon=HORIZON, min_history=min_history
    )
    report = split_report(
        engine_label, results, horizon=HORIZON, split_date=SPLIT_DATE
    )
    final = verdict(report.holdout.mean_ic, report.holdout.t_stat)

    lines = [
        f"# {report_title}",
        "",
        f"Ejecutado el {date.today().isoformat()} sobre el universo "
        f"congelado ({len(UNIVERSE)} tickers, yfinance desde {START}).",
        "",
        "## Metodología",
        "",
        f"- Horizonte {HORIZON} sesiones no solapadas; score solo con datos "
        "hasta t (T-1 estricto).",
        "- IC = Spearman transversal por fecha; spread L-S = terciles.",
        f"- Corte de diseño out-of-sample: {SPLIT_DATE.isoformat()}.",
        f"- Criterio pre-registrado: PASA t>={PASS_T_STAT}; MARGINAL "
        f"[{MARGINAL_T_STAT}, {PASS_T_STAT}); FALLA <{MARGINAL_T_STAT}.",
    ]
    if design_notes:
        lines += ["", "## Diseño del motor", ""] + [f"- {n}" for n in design_notes]
    lines += [
        "",
        "## Resultados",
        "",
        "| Periodo | Fechas | IC medio | IC std | t-stat | % IC>0 | Spread L-S (21d) |",
        "|---|---|---|---|---|---|---|",
    ]
    for stats in (report.development, report.holdout):
        lines.append(
            f"| {stats.label} | {stats.n_dates} | {stats.mean_ic:+.4f} | "
            f"{stats.std_ic:.4f} | {stats.t_stat:+.2f} | "
            f"{stats.pct_ic_positive:.0%} | {stats.mean_ls_spread:+.4f} |"
        )
    lines += ["", f"## Veredicto: {final}", "", VERDICT_TEXT[final], ""]
    markdown = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    print(markdown)
    return report, final
