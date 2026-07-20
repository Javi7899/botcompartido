"""Smoke en vivo del Supervisor IA (Fase 5). Requiere ANTHROPIC_API_KEY.

    python scripts/supervisor_smoke.py

Presenta dos operaciones-candidato a Claude (una benigna, una con una
noticia de riesgo) y muestra la decisión confirm/veto con su
justificación. El supervisor no es backtesteable (Enmienda 7): su
validación real es el paper trading; este script solo verifica que la
integración con la API funciona de punta a punta.
"""

import os
import sys
from datetime import datetime, timezone

from quantbot.config import load_config
from quantbot.data.news import NewsItemRecord
from quantbot.db.models import EngineName
from quantbot.supervisor import AnthropicClient, Supervisor
from quantbot.supervisor.supervisor import TradeCandidate


def news(title: str, hours_ago: float) -> NewsItemRecord:
    return NewsItemRecord(
        ticker="TEST",
        source="yahoo_ticker_rss",
        title=title,
        link=f"https://x.test/{abs(hash(title))}",
        published_at=datetime.now(timezone.utc).replace(microsecond=0),
    )


CANDIDATES = [
    TradeCandidate(
        ticker="AAPL",
        combined_score=0.42,
        engine_scores={EngineName.TECHNICAL: 0.5, EngineName.MACRO_NEWS: 0.3},
        engine_justifications={EngineName.TECHNICAL: "close sobre SMA200"},
        news=(news("Apple sube tras buenos resultados trimestrales", 3.0),),
    ),
    TradeCandidate(
        ticker="XYZ",
        combined_score=0.38,
        engine_scores={EngineName.TECHNICAL: 0.4, EngineName.FUNDAMENTAL: 0.36},
        news=(
            news(
                "La FDA decide mañana sobre el fármaco estrella de XYZ; "
                "el 80% de sus ingresos depende del resultado",
                2.0,
            ),
        ),
    ),
]


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "Falta ANTHROPIC_API_KEY. Exporta la clave y reintenta.\n"
            "El supervisor se valida en paper trading (Fase 8); este smoke "
            "solo comprueba la integración con la API."
        )
        return 1

    config = load_config()
    supervisor = Supervisor(AnthropicClient(model=config.supervisor_model))
    print(f"Modelo: {config.supervisor_model}\n")
    for candidate in CANDIDATES:
        verdict = supervisor.review(candidate)
        print(f"[{verdict.decision.upper()}] {candidate.ticker}")
        print(f"  justificación: {verdict.justification}")
        print(f"  request_id: {verdict.request_id}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
