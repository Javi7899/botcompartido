"""Supervisor: builds the versioned prompt, calls the LLM, parses the
confirm/veto decision, and produces a persistable verdict (Capa 2.3).

Authority is confirm-or-veto ONLY (spec 2.3): the supervisor can never
propose a trade the engines didn't suggest. A veto must always carry a
textual justification (enforced here and by the DB constraint).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources

from pydantic import BaseModel, ConfigDict

from quantbot.data.news import NewsItemRecord
from quantbot.db.models import EngineName, SupervisorDecision
from quantbot.supervisor.llm_client import LLMClient

PROMPT_VERSION = "v1"

# Structured-outputs schema — guarantees a parseable decision (no prefill).
DECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["confirmed", "vetoed"]},
        "justification": {"type": "string"},
    },
    "required": ["decision", "justification"],
    "additionalProperties": False,
}


def load_prompt(version: str = PROMPT_VERSION) -> str:
    """Load the versioned system prompt from the package (spec 2.3:
    the exact prompt is versioned in the repo)."""
    return (
        resources.files("quantbot.supervisor.prompts")
        .joinpath(f"{version}.md")
        .read_text(encoding="utf-8")
    )


@dataclass(frozen=True)
class TradeCandidate:
    """A trade the engines suggested, presented to the committee."""

    ticker: str
    combined_score: float
    engine_scores: Mapping[EngineName, float]
    engine_justifications: Mapping[EngineName, str] = field(default_factory=dict)
    news: tuple[NewsItemRecord, ...] = ()


class SupervisorVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    decision: str  # "confirmed" | "vetoed"
    justification: str
    model_name: str
    prompt_version: str
    prompt_text: str
    response_text: str
    request_id: str | None = None

    @property
    def vetoed(self) -> bool:
        return self.decision == "vetoed"


def build_user_message(candidate: TradeCandidate) -> str:
    lines = [
        f"Activo: {candidate.ticker}",
        f"Score final ponderado (post-bayesiano): {candidate.combined_score:+.3f}",
        "",
        "Scores individuales de los motores:",
    ]
    for engine, score in candidate.engine_scores.items():
        justification = candidate.engine_justifications.get(engine, "")
        suffix = f" — {justification}" if justification else ""
        lines.append(f"  - {engine.value}: {score:+.3f}{suffix}")
    lines.append("")
    if candidate.news:
        lines.append("Noticias recientes (más nuevas primero):")
        for item in candidate.news:
            lines.append(f"  - [{item.published_iso()}] {item.title}")
    else:
        lines.append("Noticias recientes: ninguna en la ventana.")
    lines.append("")
    lines.append(
        "¿Confirmas o vetas esta operación? Responde con el JSON del esquema."
    )
    return "\n".join(lines)


class Supervisor:
    def __init__(
        self, client: LLMClient, *, prompt_version: str = PROMPT_VERSION
    ) -> None:
        self.client = client
        self.prompt_version = prompt_version
        self.prompt_text = load_prompt(prompt_version)

    def review(self, candidate: TradeCandidate) -> SupervisorVerdict:
        user = build_user_message(candidate)
        response = self.client.complete(
            self.prompt_text, user, DECISION_SCHEMA
        )
        decision, justification = self._parse(response.text, candidate.ticker)
        return SupervisorVerdict(
            ticker=candidate.ticker,
            decision=decision,
            justification=justification,
            model_name=response.model,
            prompt_version=self.prompt_version,
            prompt_text=self.prompt_text,
            response_text=response.text,
            request_id=response.request_id,
        )

    @staticmethod
    def _parse(text: str, ticker: str) -> tuple[str, str]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{ticker}: respuesta del supervisor no es JSON válido: {exc}"
            ) from exc
        decision = payload.get("decision")
        justification = (payload.get("justification") or "").strip()
        if decision not in ("confirmed", "vetoed"):
            raise ValueError(
                f"{ticker}: decisión inválida del supervisor: {decision!r}"
            )
        # Un veto sin justificación es inválido (spec 2.3), igual que el
        # constraint de la tabla supervisor_decisions.
        if decision == "vetoed" and not justification:
            raise ValueError(
                f"{ticker}: veto sin justificación textual (prohibido)"
            )
        return decision, justification


def to_row(verdict: SupervisorVerdict, run_id: int, created_at_utc: str) -> SupervisorDecision:
    """Map a verdict to its immutable DB row (persisted per spec 2.3/4.3)."""
    return SupervisorDecision(
        run_id=run_id,
        ticker=verdict.ticker,
        model_name=verdict.model_name,
        prompt_version=verdict.prompt_version,
        prompt_text=verdict.prompt_text,
        response_text=verdict.response_text,
        decision=verdict.decision,
        justification=verdict.justification,
        created_at_utc=created_at_utc,
    )
