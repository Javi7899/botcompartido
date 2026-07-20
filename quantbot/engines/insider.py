"""Insider engine (spec 2.1.5) — motor 5 de la tabla 0.0. LIVE-ONLY.

Régimen (Enmienda v1.2): sin backtest histórico — el volumen de datos de
Form 4 necesario es inviable con fuentes gratuitas en este proyecto — así
que recibe el tratamiento 0.1: peso bayesiano inicial conservador,
persistencia diaria de predicciones y validación en paper trading.

Diseño (parámetros FIJOS a priori):
- Ventana: transacciones de los últimos 90 días naturales.
- Solo mercado abierto: código P (compra) y S (venta). Se excluyen M
  (ejercicio de opciones), F (retención fiscal), G (regalos), A (awards),
  etc., y cualquier transacción bajo plan Rule 10b5-1 (rutinaria).
- Señal por transacción: valor en dólares (acciones × precio) × peso de
  rol × decaimiento por antigüedad (semivida 30 días). Las ventas pesan
  0.25× (venden por mil motivos; compran por uno).
- Roles: CEO/CFO 1.0 · otros officers 0.7 · directores 0.5 · 10% owners
  0.5 (spec: seniority pondera).
- Score = tanh(neto ponderado / $2M). Sin transacciones → score 0 (la
  ausencia de actividad es información neutra, no dato faltante).
"""

from collections.abc import Sequence
from datetime import date
from math import tanh
from typing import ClassVar

from quantbot.data.edgar import InsiderTransaction
from quantbot.db.models import EngineName
from quantbot.engines.base import EngineResult

DATA_SOURCE = "SEC EDGAR Form 4 (live-only, delay de reporte <=2 dias habiles)"

LOOKBACK_DAYS = 90
HALF_LIFE_DAYS = 30.0
SALE_WEIGHT = 0.25
DOLLAR_NORMALIZER = 2_000_000.0

# "president" a secas colisionaría con "vice president"; se omite adrede.
SENIOR_TITLES = ("chief executive", "chief financial", "ceo", "cfo")


def role_weight(txn: InsiderTransaction) -> float:
    title = txn.officer_title.lower()
    if txn.is_officer and any(t in title for t in SENIOR_TITLES):
        return 1.0
    if txn.is_officer:
        return 0.7
    if txn.is_director or txn.is_ten_percent_owner:
        return 0.5
    return 0.3


class InsiderEngine:
    name: ClassVar[EngineName] = EngineName.INSIDER
    version: ClassVar[str] = "1.0-form4-weighted"

    def score_ticker(
        self,
        ticker: str,
        transactions: Sequence[InsiderTransaction],
        as_of: date,
    ) -> EngineResult:
        net_weighted = 0.0
        purchases = sales = ignored = 0
        for txn in transactions:
            age = (as_of - txn.transaction_date).days
            if age < 0 or age > LOOKBACK_DAYS:
                ignored += 1
                continue
            if txn.code not in ("P", "S") or txn.rule_10b5_1:
                ignored += 1
                continue
            if txn.price is None:
                ignored += 1
                continue
            dollars = txn.shares * txn.price
            decay = 0.5 ** (age / HALF_LIFE_DAYS)
            weight = role_weight(txn) * decay
            if txn.code == "P" and txn.acquired:
                net_weighted += dollars * weight
                purchases += 1
            elif txn.code == "S" and not txn.acquired:
                net_weighted -= dollars * weight * SALE_WEIGHT
                sales += 1
            else:
                # código y sentido incoherentes (P con D o S con A): ruido
                ignored += 1

        score = max(-1.0, min(1.0, tanh(net_weighted / DOLLAR_NORMALIZER)))
        if purchases == 0 and sales == 0:
            justification = (
                f"[{self.version}] sin transacciones de mercado abierto "
                f"relevantes en {LOOKBACK_DAYS} días "
                f"({ignored} descartadas: no-P/S, 10b5-1 o sin precio)"
            )
        else:
            justification = (
                f"[{self.version}] {purchases} compras / {sales} ventas en "
                f"{LOOKBACK_DAYS} días; neto ponderado por rol y "
                f"antigüedad {net_weighted:+,.0f} USD "
                f"({ignored} descartadas)"
            )
        return EngineResult(
            engine=self.name,
            ticker=ticker,
            score=score,
            justification=justification,
            data_source=DATA_SOURCE,
        )
