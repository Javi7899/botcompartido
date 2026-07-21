"""Whole-share rounding with position limits (Enmienda 1).

MOC orders on IBKR do not allow fractional shares, so BL/Kelly target
weights must be converted to WHOLE shares. The universe is the candidate
set, not the portfolio: at most ``max_positions`` names are held, and a
ticker whose single-share price exceeds the target position size is
NON-INVESTABLE with this capital (documented and excluded).
"""

from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_MAX_POSITIONS = 15  # dentro del rango 10-20 del spec
DEFAULT_MIN_POSITION_USD = 300.0  # tamaño mínimo de posición (~$300)


@dataclass(frozen=True)
class TargetPosition:
    ticker: str
    target_weight: float
    price: float
    shares: int
    dollar_value: float
    investable: bool
    note: str


@dataclass(frozen=True)
class SizingResult:
    """Posiciones finales (todas invertibles) y las descartadas con su
    motivo — la traza de por qué cada candidato quedó fuera se conserva
    (principio de trazabilidad del proyecto)."""

    positions: list[TargetPosition]
    excluded: list[TargetPosition]

    @property
    def invested_value(self) -> float:
        return sum(p.dollar_value for p in self.positions)


def round_to_shares(
    target_weights: Mapping[str, float],
    prices: Mapping[str, float],
    capital: float,
    *,
    exposure: float = 1.0,
    max_positions: int = DEFAULT_MAX_POSITIONS,
    min_position_usd: float = DEFAULT_MIN_POSITION_USD,
) -> SizingResult:
    """Convert target weights to whole-share positions.

    ``exposure`` (from fractional Kelly) scales how much capital is deployed;
    the rest stays in cash. Positions are selected by weight (largest first),
    each funded to at least ``min_position_usd``. Tickers priced above their
    allocation are marked non-investable.

    The position COUNT is derived from the deployable capital, not fixed:
    n = min(max_positions, deployable // min_position_usd). This is load-
    bearing — with a fixed count, fractional Kelly (which typically deploys
    well under 100% of a $5.000 account) would slice the capital into
    allocations smaller than a single share and every position would come
    back non-investable. Deriving the count concentrates the deployable
    capital into the best signals, exactly as Enmienda 1 intends.
    """
    if capital <= 0:
        raise ValueError(f"capital no positivo: {capital}")
    if not 0 <= exposure <= 1:
        raise ValueError(f"exposure fuera de [0, 1]: {exposure}")

    deployable = capital * exposure
    ranked = sorted(
        (t for t, w in target_weights.items() if w > 0),
        key=lambda t: target_weights[t],
        reverse=True,
    )

    affordable = int(deployable // min_position_usd)
    if affordable < 1:
        return SizingResult([], [])  # desplegable insuficiente: todo cash

    # Se prueba de más a menos posiciones y se toma la primera configuración
    # donde TODAS son invertibles. Dividir por el mínimo no basta: tras
    # redondear a acciones enteras, una asignación de $383 en un título de
    # $200 solo compra 1 acción ($200), que queda bajo el mínimo. Reducir el
    # número concentra más capital por posición hasta que caben.
    upper = min(max_positions, affordable, len(ranked))
    widest = _build_positions(
        ranked[:upper], target_weights, prices, deployable, min_position_usd
    )
    for count in range(upper, 0, -1):
        attempt = _build_positions(
            ranked[:count], target_weights, prices, deployable, min_position_usd
        )
        if attempt and all(p.investable for p in attempt):
            chosen = {p.ticker for p in attempt}
            excluded = [p for p in widest if p.ticker not in chosen]
            return SizingResult(attempt, excluded)
    # Ninguna configuración viable: todo cash, con la traza del intento
    # más amplio para saber por qué.
    return SizingResult([], widest)


def _build_positions(
    selected: list[str],
    target_weights: Mapping[str, float],
    prices: Mapping[str, float],
    deployable: float,
    min_position_usd: float,
) -> list[TargetPosition]:
    """Round one candidate selection to whole shares."""
    positions: list[TargetPosition] = []
    if not selected:
        return positions
    # Renormalizar los pesos de los seleccionados para que sumen 1.
    selected_weight = sum(target_weights[t] for t in selected)

    for ticker in selected:
        price = prices.get(ticker)
        weight = target_weights[ticker]
        if price is None or price <= 0:
            positions.append(
                TargetPosition(
                    ticker, weight, price or 0.0, 0, 0.0, False,
                    "sin precio válido",
                )
            )
            continue
        allocation = deployable * (weight / selected_weight)
        if price > allocation:
            # Ni una acción entera cabe en la asignación: no invertible.
            positions.append(
                TargetPosition(
                    ticker, weight, price, 0, 0.0, False,
                    f"precio/acción {price:.2f} > asignación "
                    f"{allocation:.2f} (no invertible con este capital)",
                )
            )
            continue
        shares = int(allocation // price)
        value = shares * price
        if value < min_position_usd:
            positions.append(
                TargetPosition(
                    ticker, weight, price, 0, 0.0, False,
                    f"posición {value:.2f} < mínimo {min_position_usd:.0f}",
                )
            )
            continue
        positions.append(
            TargetPosition(
                ticker, weight, price, shares, value, True,
                f"{shares} acciones = {value:.2f} USD",
            )
        )
    return positions
