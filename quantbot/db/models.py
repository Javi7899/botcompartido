"""SQLAlchemy ORM models for the traceability database (spec section 4.3).

Every quantity the pipeline computes is persisted here, including on days
when no orders are sent (spec 1.1). Timestamps are stored as ISO-8601 TEXT:
``*_utc`` columns in UTC (sortable), ``*_et`` columns with the market-timezone
offset for human traceability.

Immutability: the pure-trace tables (predictions, weights, supervisor
decisions, portfolio targets, fills) are append-only, enforced with SQLite
triggers created in ``init_db`` — an UPDATE or DELETE raises instead of
silently rewriting history. ``pipeline_runs`` and ``broker_orders`` are the
two mutable exceptions: a run row is opened at start and closed at the end
(orders_sent/abort_reason), and an order row tracks its lifecycle status.
"""

import enum

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EngineName(str, enum.Enum):
    """The 7 signal engines, in build order (spec table 0.0)."""

    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    TIME_SERIES = "time_series"
    ML_XGBOOST = "ml_xgboost"
    INSIDER = "insider"
    GEX = "gex"
    MACRO_NEWS = "macro_news"


class OrderStatus(str, enum.Enum):
    """Order lifecycle (spec 4.4: state persisted before any retry)."""

    PENDING = "pending"
    SENT = "sent"
    CONFIRMED = "confirmed"
    FILLED = "filled"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ENGINE_VALUES = ", ".join(f"'{e.value}'" for e in EngineName)
_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in OrderStatus)


class PipelineRun(Base):
    """One row per bot execution (spec 1.1: exact run time is recorded daily)."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at_utc: Mapped[str]
    started_at_et: Mapped[str]
    # Trading session (YYYY-MM-DD, market date) the run targets.
    trading_date: Mapped[str]
    environment: Mapped[str]
    finished_at_utc: Mapped[str | None] = mapped_column(default=None)
    orders_sent: Mapped[bool] = mapped_column(default=False)
    # Non-null when order submission was aborted (market closed, no time
    # margin before the MOC cutoff, broker unreachable, ...). The rest of the
    # pipeline still runs and persists (spec 1.1).
    orders_abort_reason: Mapped[str | None] = mapped_column(Text, default=None)

    predictions: Mapped[list["EnginePrediction"]] = relationship(back_populates="run")


class EnginePrediction(Base):
    """Daily score of one engine for one ticker (append-only)."""

    __tablename__ = "engine_predictions"
    __table_args__ = (
        CheckConstraint("score >= -1.0 AND score <= 1.0", name="score_range"),
        CheckConstraint(f"engine IN ({_ENGINE_VALUES})", name="engine_valid"),
        UniqueConstraint("run_id", "engine", "ticker", name="uq_run_engine_ticker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    engine: Mapped[str]
    ticker: Mapped[str]
    score: Mapped[float]
    justification: Mapped[str] = mapped_column(Text)
    data_source: Mapped[str]
    created_at_utc: Mapped[str]

    run: Mapped[PipelineRun] = relationship(back_populates="predictions")


class BayesianWeight(Base):
    """Hierarchical weight of an engine (Capa 2.2). ticker=NULL is the global
    prior; a non-null ticker is the per-asset posterior (append-only)."""

    __tablename__ = "bayesian_weights"
    __table_args__ = (
        CheckConstraint("weight >= 0.0", name="weight_non_negative"),
        CheckConstraint(f"engine IN ({_ENGINE_VALUES})", name="engine_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    engine: Mapped[str]
    ticker: Mapped[str | None] = mapped_column(default=None)
    weight: Mapped[float]
    # Number of observations backing this weight (drives shrinkage).
    evidence_count: Mapped[int] = mapped_column(default=0)
    created_at_utc: Mapped[str]


class SupervisorDecision(Base):
    """Immutable record of each LLM supervisor decision (Capa 2.3)."""

    __tablename__ = "supervisor_decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('confirmed', 'vetoed')", name="decision_valid"),
        # Spec 2.3: a veto must always carry a textual justification.
        CheckConstraint(
            "decision != 'vetoed' OR length(justification) > 0",
            name="veto_requires_justification",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    ticker: Mapped[str]
    model_name: Mapped[str]
    prompt_version: Mapped[str]
    prompt_text: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str] = mapped_column(Text)
    decision: Mapped[str]
    justification: Mapped[str] = mapped_column(Text)
    created_at_utc: Mapped[str]


class PortfolioTarget(Base):
    """Target allocation per ticker after Black-Litterman + fractional Kelly
    (Fase 6), rounded to whole shares (Enmienda 1). Append-only."""

    __tablename__ = "portfolio_targets"
    __table_args__ = (
        CheckConstraint("target_shares >= 0", name="shares_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    ticker: Mapped[str]
    bl_weight: Mapped[float]
    kelly_fraction: Mapped[float]
    target_weight: Mapped[float]
    target_shares: Mapped[int]
    created_at_utc: Mapped[str]


class BrokerOrder(Base):
    """Order sent (or attempted) to IBKR. Mutable only in its status fields;
    never re-sent without first reconciling against the broker (spec 4.4)."""

    __tablename__ = "broker_orders"
    __table_args__ = (
        CheckConstraint("side IN ('buy', 'sell')", name="side_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    ticker: Mapped[str]
    side: Mapped[str]
    quantity: Mapped[int]
    order_type: Mapped[str] = mapped_column(default="MOC")
    status: Mapped[str] = mapped_column(default=OrderStatus.PENDING.value)
    ib_order_id: Mapped[str | None] = mapped_column(default=None)
    created_at_utc: Mapped[str]
    updated_at_utc: Mapped[str]

    fills: Mapped[list["Fill"]] = relationship(back_populates="order")


class Fill(Base):
    """Real broker fill, reconciled next day against IBKR (append-only)."""

    __tablename__ = "fills"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="fill_quantity_positive"),
        CheckConstraint("price > 0", name="fill_price_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("broker_orders.id"))
    quantity: Mapped[int]
    price: Mapped[float]
    executed_at_utc: Mapped[str]
    reconciled_at_utc: Mapped[str]

    order: Mapped[BrokerOrder] = relationship(back_populates="fills")


# Tables protected against UPDATE/DELETE via SQLite triggers (see init_db).
IMMUTABLE_TABLES: tuple[str, ...] = (
    "engine_predictions",
    "bayesian_weights",
    "supervisor_decisions",
    "portfolio_targets",
    "fills",
)
