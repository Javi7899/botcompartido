from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from quantbot.db import (
    BayesianWeight,
    BrokerOrder,
    EngineName,
    EnginePrediction,
    Fill,
    OrderStatus,
    PipelineRun,
    PortfolioTarget,
    SupervisorDecision,
)
from quantbot.time_utils import iso_market, iso_utc

NOW = datetime(2026, 7, 17, 19, 30, tzinfo=timezone.utc)


def make_run() -> PipelineRun:
    return PipelineRun(
        started_at_utc=iso_utc(NOW),
        started_at_et=iso_market(NOW),
        trading_date="2026-07-17",
        environment="dev",
    )


EXPECTED_TABLES = {
    "pipeline_runs",
    "engine_predictions",
    "bayesian_weights",
    "supervisor_decisions",
    "portfolio_targets",
    "broker_orders",
    "fills",
}


def test_init_db_creates_all_tables(db_engine) -> None:
    assert EXPECTED_TABLES <= set(inspect(db_engine).get_table_names())


def test_full_traceability_chain(db_session: Session) -> None:
    """A run with prediction, weight, decision, target, order and fill persists."""
    run = make_run()
    db_session.add(run)
    db_session.flush()

    db_session.add_all(
        [
            EnginePrediction(
                run_id=run.id,
                engine=EngineName.TECHNICAL.value,
                ticker="AAPL",
                score=0.42,
                justification="RSI y MACD alcistas",
                data_source="yfinance",
                created_at_utc=iso_utc(NOW),
            ),
            BayesianWeight(
                run_id=run.id,
                engine=EngineName.TECHNICAL.value,
                ticker=None,
                weight=0.3,
                evidence_count=100,
                created_at_utc=iso_utc(NOW),
            ),
            SupervisorDecision(
                run_id=run.id,
                ticker="AAPL",
                model_name="claude-fable-5",
                prompt_version="v1",
                prompt_text="prompt completo",
                response_text="respuesta completa",
                decision="confirmed",
                justification="sin noticias en contra",
                created_at_utc=iso_utc(NOW),
            ),
            PortfolioTarget(
                run_id=run.id,
                ticker="AAPL",
                bl_weight=0.08,
                kelly_fraction=0.25,
                target_weight=0.06,
                target_shares=2,
                created_at_utc=iso_utc(NOW),
            ),
        ]
    )
    order = BrokerOrder(
        run_id=run.id,
        ticker="AAPL",
        side="buy",
        quantity=2,
        created_at_utc=iso_utc(NOW),
        updated_at_utc=iso_utc(NOW),
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        Fill(
            order_id=order.id,
            quantity=2,
            price=231.5,
            executed_at_utc=iso_utc(NOW),
            reconciled_at_utc=iso_utc(NOW),
        )
    )
    db_session.commit()

    stored = db_session.execute(select(PipelineRun)).scalar_one()
    assert stored.predictions[0].ticker == "AAPL"
    assert stored.orders_sent is False
    assert order.status == OrderStatus.PENDING.value
    assert order.order_type == "MOC"
    assert order.fills[0].price == 231.5


def test_score_out_of_range_rejected(db_session: Session) -> None:
    run = make_run()
    db_session.add(run)
    db_session.flush()
    db_session.add(
        EnginePrediction(
            run_id=run.id,
            engine=EngineName.TECHNICAL.value,
            ticker="AAPL",
            score=1.5,
            justification="x",
            data_source="yfinance",
            created_at_utc=iso_utc(NOW),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_unknown_engine_rejected(db_session: Session) -> None:
    run = make_run()
    db_session.add(run)
    db_session.flush()
    db_session.add(
        EnginePrediction(
            run_id=run.id,
            engine="reinforcement_learning",  # eliminado por la Enmienda 5
            ticker="AAPL",
            score=0.1,
            justification="x",
            data_source="x",
            created_at_utc=iso_utc(NOW),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_foreign_key_enforced(db_session: Session) -> None:
    db_session.add(
        EnginePrediction(
            run_id=99999,
            engine=EngineName.GEX.value,
            ticker="SPY",
            score=0.0,
            justification="x",
            data_source="x",
            created_at_utc=iso_utc(NOW),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_prediction_same_run_rejected(db_session: Session) -> None:
    run = make_run()
    db_session.add(run)
    db_session.flush()
    for _ in range(2):
        db_session.add(
            EnginePrediction(
                run_id=run.id,
                engine=EngineName.TECHNICAL.value,
                ticker="AAPL",
                score=0.1,
                justification="x",
                data_source="x",
                created_at_utc=iso_utc(NOW),
            )
        )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_veto_without_justification_rejected(db_session: Session) -> None:
    run = make_run()
    db_session.add(run)
    db_session.flush()
    db_session.add(
        SupervisorDecision(
            run_id=run.id,
            ticker="AAPL",
            model_name="claude-fable-5",
            prompt_version="v1",
            prompt_text="p",
            response_text="r",
            decision="vetoed",
            justification="",
            created_at_utc=iso_utc(NOW),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_immutable_tables_reject_update_and_delete(db_session: Session) -> None:
    run = make_run()
    db_session.add(run)
    db_session.flush()
    prediction = EnginePrediction(
        run_id=run.id,
        engine=EngineName.TECHNICAL.value,
        ticker="AAPL",
        score=0.42,
        justification="x",
        data_source="x",
        created_at_utc=iso_utc(NOW),
    )
    db_session.add(prediction)
    db_session.commit()

    prediction.score = -0.9
    with pytest.raises(IntegrityError, match="append-only"):
        db_session.commit()
    db_session.rollback()

    db_session.delete(prediction)
    with pytest.raises(IntegrityError, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_pipeline_run_is_updatable(db_session: Session) -> None:
    """pipeline_runs is a deliberate exception: the row opened at start is
    closed at the end of the run (spec: abort is recorded, pipeline persists)."""
    run = make_run()
    db_session.add(run)
    db_session.commit()

    run.orders_sent = False
    run.orders_abort_reason = "margen insuficiente antes del cutoff MOC"
    run.finished_at_utc = iso_utc(NOW)
    db_session.commit()

    stored = db_session.execute(select(PipelineRun)).scalar_one()
    assert stored.orders_abort_reason is not None


def test_order_status_transition_and_invalid_status(db_session: Session) -> None:
    run = make_run()
    db_session.add(run)
    db_session.flush()
    order = BrokerOrder(
        run_id=run.id,
        ticker="MSFT",
        side="sell",
        quantity=1,
        created_at_utc=iso_utc(NOW),
        updated_at_utc=iso_utc(NOW),
    )
    db_session.add(order)
    db_session.commit()

    order.status = OrderStatus.SENT.value
    db_session.commit()
    assert order.status == "sent"

    order.status = "teleported"
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
