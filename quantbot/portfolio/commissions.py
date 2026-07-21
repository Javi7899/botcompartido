"""IBKR commission model and rebalance filter (spec 3, Enmienda 6).

IBKR Pro Fixed (US stocks): $0.005 per share, minimum $1.00 per order,
capped at 1% of trade value. With $5.000 and small adjustments, the $1
minimum dominates (1-3% of a small trade) — by design the filter blocks
most small rebalances (Enmienda 6: low rotation is expected, not a bug).

Rebalance filter (spec 3): an order is only generated when BOTH hold:
1. |current weight − target weight| exceeds a minimum threshold.
2. Expected benefit of the adjustment ≥ 3× the estimated commission.

The application LEVEL is configurable (spec 3, decided/tested in Fase 6):
- INDIVIDUAL: each position must clear the bar on its own.
- AGGREGATE: the whole day's rebalance is evaluated together; small
  individual adjustments execute if the aggregate clears the bar.
"""

import enum
from dataclasses import dataclass

PER_SHARE = 0.005
MIN_COMMISSION = 1.00
MAX_COMMISSION_PCT = 0.01  # 1% del valor de la operación

DEFAULT_DEVIATION_THRESHOLD = 0.01  # 1 punto porcentual
DEFAULT_BENEFIT_MULTIPLE = 3.0  # beneficio esperado >= 3x comisión


def ibkr_commission(shares: int, price: float) -> float:
    """Fixed-tier commission for a US-stock order. shares is the absolute
    number traded (buy or sell)."""
    if shares <= 0:
        return 0.0
    if price <= 0:
        raise ValueError(f"precio no positivo: {price}")
    raw = PER_SHARE * shares
    trade_value = shares * price
    capped = min(max(raw, MIN_COMMISSION), MAX_COMMISSION_PCT * trade_value)
    # El cap del 1% puede quedar por debajo del mínimo de $1 en operaciones
    # muy pequeñas; IBKR aplica el cap, así que respetamos ese orden.
    return capped


class FilterMode(str, enum.Enum):
    INDIVIDUAL = "individual"
    AGGREGATE = "aggregate"


@dataclass(frozen=True)
class RebalanceDecision:
    ticker: str
    current_shares: int
    target_shares: int
    delta_shares: int  # + comprar, − vender
    price: float
    commission: float
    expected_benefit: float
    weight_deviation: float
    execute: bool
    reason: str


class CommissionFilter:
    def __init__(
        self,
        *,
        mode: FilterMode = FilterMode.INDIVIDUAL,
        deviation_threshold: float = DEFAULT_DEVIATION_THRESHOLD,
        benefit_multiple: float = DEFAULT_BENEFIT_MULTIPLE,
    ) -> None:
        self.mode = mode
        self.deviation_threshold = deviation_threshold
        self.benefit_multiple = benefit_multiple

    def evaluate(
        self,
        *,
        ticker: str,
        current_shares: int,
        target_shares: int,
        price: float,
        expected_edge: float,
        portfolio_value: float,
    ) -> RebalanceDecision:
        """Evaluate ONE position. ``expected_edge`` is the expected fractional
        return improvement from moving this position to target (used to size
        the benefit). In INDIVIDUAL mode the returned ``execute`` is final; in
        AGGREGATE mode the caller overrides it via :meth:`apply_aggregate`."""
        delta = target_shares - current_shares
        commission = ibkr_commission(abs(delta), price)
        trade_value = abs(delta) * price
        expected_benefit = abs(expected_edge) * trade_value
        deviation = (
            trade_value / portfolio_value if portfolio_value > 0 else 0.0
        )

        if delta == 0:
            execute, reason = False, "sin cambio de posición"
        elif deviation < self.deviation_threshold:
            execute = False
            reason = (
                f"desviación {deviation:.2%} < umbral "
                f"{self.deviation_threshold:.2%}"
            )
        elif expected_benefit < self.benefit_multiple * commission:
            execute = False
            reason = (
                f"beneficio {expected_benefit:.2f} < "
                f"{self.benefit_multiple:g}x comisión "
                f"({self.benefit_multiple * commission:.2f})"
            )
        else:
            execute, reason = True, "supera umbral y regla de comisión"

        return RebalanceDecision(
            ticker=ticker,
            current_shares=current_shares,
            target_shares=target_shares,
            delta_shares=delta,
            price=price,
            commission=commission,
            expected_benefit=expected_benefit,
            weight_deviation=deviation,
            execute=execute if self.mode == FilterMode.INDIVIDUAL else False,
            reason=reason,
        )

    def apply_aggregate(
        self, decisions: list[RebalanceDecision]
    ) -> list[RebalanceDecision]:
        """AGGREGATE mode: if the total expected benefit of all non-trivial
        adjustments clears 3× the total commission AND the aggregate turnover
        clears the threshold, execute every non-zero-delta position."""
        if self.mode != FilterMode.AGGREGATE:
            raise ValueError("apply_aggregate solo en modo AGGREGATE")
        movers = [d for d in decisions if d.delta_shares != 0]
        total_commission = sum(d.commission for d in movers)
        total_benefit = sum(d.expected_benefit for d in movers)
        total_deviation = sum(d.weight_deviation for d in movers)

        aggregate_ok = (
            total_deviation >= self.deviation_threshold
            and total_benefit >= self.benefit_multiple * total_commission
        )
        reason = (
            "rebalanceo agregado supera umbral y regla"
            if aggregate_ok
            else "rebalanceo agregado no supera umbral/regla"
        )
        result = []
        for d in decisions:
            execute = aggregate_ok and d.delta_shares != 0
            result.append(
                RebalanceDecision(
                    ticker=d.ticker,
                    current_shares=d.current_shares,
                    target_shares=d.target_shares,
                    delta_shares=d.delta_shares,
                    price=d.price,
                    commission=d.commission,
                    expected_benefit=d.expected_benefit,
                    weight_deviation=d.weight_deviation,
                    execute=execute,
                    reason=reason if d.delta_shares != 0 else "sin cambio",
                )
            )
        return result
