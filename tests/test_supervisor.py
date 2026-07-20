import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from quantbot.data.news import NewsItemRecord
from quantbot.db.models import EngineName, PipelineRun, SupervisorDecision
from quantbot.supervisor.llm_client import LLMResponse
from quantbot.supervisor.supervisor import (
    DECISION_SCHEMA,
    Supervisor,
    TradeCandidate,
    build_user_message,
    load_prompt,
    to_row,
)

TECH = EngineName.TECHNICAL
NEWS = EngineName.MACRO_NEWS


class FakeLLM:
    """Devuelve una respuesta fija y registra lo que recibió."""

    def __init__(self, payload: dict, model: str = "claude-opus-4-8-fake") -> None:
        self.model = model
        self._payload = payload
        self.last_system: str | None = None
        self.last_user: str | None = None
        self.last_schema: dict | None = None

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse:
        self.last_system, self.last_user, self.last_schema = system, user, schema
        return LLMResponse(
            model=self.model, text=json.dumps(self._payload), request_id="req_x"
        )


def candidate(score: float = 0.4, news=()) -> TradeCandidate:
    return TradeCandidate(
        ticker="AAPL",
        combined_score=score,
        engine_scores={TECH: 0.5, NEWS: 0.3},
        engine_justifications={TECH: "close sobre SMA200"},
        news=news,
    )


def test_prompt_versioned_and_loadable() -> None:
    prompt = load_prompt("v1")
    assert "Comité de Inversión" in prompt
    assert "confirmar o vetar" in prompt


def test_build_user_message_includes_scores_and_news() -> None:
    item = NewsItemRecord(
        ticker="AAPL",
        source="yahoo_ticker_rss",
        title="Apple beats estimates",
        link="https://x.test/1",
        published_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
    )
    message = build_user_message(candidate(news=(item,)))
    assert "AAPL" in message
    assert "+0.400" in message
    assert "technical: +0.500" in message
    assert "Apple beats estimates" in message


def test_confirm_flow() -> None:
    llm = FakeLLM({"decision": "confirmed", "justification": "sin riesgos"})
    verdict = Supervisor(llm).review(candidate())
    assert verdict.decision == "confirmed"
    assert not verdict.vetoed
    assert verdict.model_name == "claude-opus-4-8-fake"
    assert verdict.prompt_version == "v1"
    assert llm.last_schema == DECISION_SCHEMA
    # el prompt del sistema es el versionado
    assert "Comité de Inversión" in verdict.prompt_text


def test_veto_flow_persists_justification() -> None:
    llm = FakeLLM(
        {"decision": "vetoed", "justification": "ensayo clínico pendiente mañana"}
    )
    verdict = Supervisor(llm).review(candidate())
    assert verdict.vetoed
    assert "ensayo clínico" in verdict.justification


def test_veto_without_justification_rejected() -> None:
    llm = FakeLLM({"decision": "vetoed", "justification": ""})
    with pytest.raises(ValueError, match="veto sin justificación"):
        Supervisor(llm).review(candidate())


def test_invalid_decision_rejected() -> None:
    llm = FakeLLM({"decision": "maybe", "justification": "x"})
    with pytest.raises(ValueError, match="decisión inválida"):
        Supervisor(llm).review(candidate())


def test_non_json_response_rejected() -> None:
    class BadLLM:
        model = "m"

        def complete(self, system, user, schema):
            return LLMResponse(model="m", text="no soy json")

    with pytest.raises(ValueError, match="no es JSON"):
        Supervisor(BadLLM()).review(candidate())


def test_persist_to_immutable_table(db_session: Session) -> None:
    run = PipelineRun(
        started_at_utc="2026-07-20T12:00:00+00:00",
        started_at_et="2026-07-20T08:00:00-04:00",
        trading_date="2026-07-20",
        environment="dev",
    )
    db_session.add(run)
    db_session.flush()

    llm = FakeLLM({"decision": "confirmed", "justification": "ok"})
    verdict = Supervisor(llm).review(candidate())
    db_session.add(to_row(verdict, run.id, "2026-07-20T12:00:01+00:00"))
    db_session.commit()

    stored = db_session.execute(select(SupervisorDecision)).scalar_one()
    assert stored.decision == "confirmed"
    assert stored.prompt_version == "v1"
    assert "Comité de Inversión" in stored.prompt_text

    # la tabla es append-only (trigger de Fase 1)
    from sqlalchemy.exc import IntegrityError

    stored.decision = "vetoed"
    with pytest.raises(IntegrityError, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_decision_schema_is_strict() -> None:
    assert DECISION_SCHEMA["additionalProperties"] is False
    assert set(DECISION_SCHEMA["required"]) == {"decision", "justification"}
