"""Re-ejecución reproducible del backtest del motor Técnico v2 (Fase 3.1).

    python scripts/backtest_technical.py

El informe canónico del gate de Fase 3.1 — que documenta el proceso
completo (v1 FALLA -> análisis de componentes en desarrollo -> v2
confirmada one-shot como MARGINAL) — es docs/BACKTEST_MOTOR_TECNICO.md y
se mantiene a mano. Este script re-ejecuta la evaluación de la v2 con el
protocolo estándar y escribe su salida a un archivo aparte para no pisar
la historia curada. Requiere red.
"""

import sys

from quantbot.backtest.runner import run_price_engine_backtest
from quantbot.engines.technical import MIN_BARS, SMA_WINDOW, TechnicalEngine


def main() -> int:
    engine = TechnicalEngine()

    def score_fn(ticker: str, history: list[float]) -> float:
        return engine.score(ticker, history).score

    run_price_engine_backtest(
        engine_label="technical",
        score_fn=score_fn,
        min_history=MIN_BARS,
        report_title=(
            "Backtest motor Técnico v2 — re-ejecución reproducible"
        ),
        report_path="docs/BACKTEST_MOTOR_TECNICO_v2_rerun.md",
        design_notes=[
            f"score = tanh(5 × (close/SMA{SMA_WINDOW} − 1)); versión "
            f"{TechnicalEngine.version}.",
            "Informe canónico del gate: docs/BACKTEST_MOTOR_TECNICO.md.",
        ],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
