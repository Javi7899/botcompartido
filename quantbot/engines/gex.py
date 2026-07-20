"""GEX engine (spec 2.1.6) — motor 6 de la tabla 0.0. LIVE-ONLY.

Régimen (Enmienda v1.2): las cadenas de opciones históricas (OI/IV por
día) no existen en fuentes gratuitas, así que el backtest histórico es
imposible por construcción; el motor recibe el tratamiento 0.1 (peso
inicial conservador, persistencia diaria, validación en paper trading).

Convención de signo (CORREGIDA en Enmienda v1.2): la convención estándar
(SqueezeMetrics y la mayoría de herramientas públicas) asume dealers
LARGOS de calls (los clientes venden covered calls) y CORTOS de puts (los
clientes compran protección): las calls aportan gamma positiva al dealer
y las puts negativa. La v1.1 del spec tenía la convención invertida; se
corrigió para que la validación cruzada contra herramientas públicas
(nivel 3 del spec) compare signos como es debido.

Cálculo por strike (spec 2.1.6):
    GEX_strike = OI × 100 × gamma_BS × S² × 0.01   [USD por movimiento de 1%]
    con signo + para calls y − para puts.

Score del motor: balance de gamma normalizado
    score = (GEX_calls − |GEX_puts|) / (GEX_calls + |GEX_puts|)  ∈ [−1, 1]
Gamma neta positiva → régimen de "pinning"/estabilidad (los dealers
amortiguan movimientos); negativa → régimen de aceleración. Es una señal
de RÉGIMEN más que direccional — limitación documentada; su utilidad real
se medirá en paper trading.

Limitación conocida (spec 2.1.6): OI de T-1 con spot de T; un gap
intersesión grande desplaza el spot fuera de la zona representativa.
"""

from collections.abc import Mapping
from datetime import date
from math import exp, log, pi, sqrt
from typing import ClassVar

import pandas as pd
from pydantic import BaseModel, ConfigDict

from quantbot.data.errors import DataQualityError, DataSourceError
from quantbot.db.models import EngineName
from quantbot.engines.base import EngineResult

DATA_SOURCE = "cadena de opciones yfinance (OI de cierre T-1), gamma Black-Scholes"

CONTRACT_MULTIPLIER = 100
RISK_FREE_RATE = 0.04  # la gamma es casi insensible a r; fijo y documentado
MAX_EXPIRATION_DAYS = 45
MIN_TIME_YEARS = 1.0 / 365.0
IV_FLOOR = 0.01


def norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2.0 * pi)


def black_scholes_gamma(
    spot: float, strike: float, years: float, sigma: float, rate: float = RISK_FREE_RATE
) -> float:
    """Gamma of a European option (same for calls and puts)."""
    if spot <= 0 or strike <= 0 or years <= 0 or sigma <= 0:
        raise DataQualityError(
            f"inputs inválidos para gamma: S={spot}, K={strike}, "
            f"T={years}, sigma={sigma}"
        )
    d1 = (log(spot / strike) + (rate + 0.5 * sigma * sigma) * years) / (
        sigma * sqrt(years)
    )
    return norm_pdf(d1) / (spot * sigma * sqrt(years))


class GexProfile(BaseModel):
    """Aggregated gamma-exposure profile of one ticker (for traceability
    and the spec's level-3/4 validations)."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    spot: float
    call_gex: float  # USD por 1% (positivo)
    put_gex: float  # USD por 1% (negativo)
    net_gex: float
    call_wall: float | None  # strike con mayor GEX de calls
    put_wall: float | None  # strike con mayor |GEX| de puts
    gamma_flip: float | None  # strike donde el GEX neto acumulado cruza 0
    expirations_used: int

    @property
    def normalized_balance(self) -> float:
        total = self.call_gex + abs(self.put_gex)
        if total <= 0:
            return 0.0
        return (self.call_gex - abs(self.put_gex)) / total


def compute_gex_profile(
    ticker: str,
    spot: float,
    chains: Mapping[str, tuple[pd.DataFrame, pd.DataFrame]],
    as_of: date,
) -> GexProfile:
    """``chains``: expiration (YYYY-MM-DD) -> (calls, puts) frames with
    columns strike / openInterest / impliedVolatility."""
    if spot <= 0:
        raise DataSourceError(f"{ticker}: spot inválido ({spot})")
    per_strike: dict[float, float] = {}
    call_by_strike: dict[float, float] = {}
    put_by_strike: dict[float, float] = {}
    expirations_used = 0

    for expiration_str, (calls, puts) in chains.items():
        expiration = date.fromisoformat(expiration_str)
        days = (expiration - as_of).days
        if days < 0 or days > MAX_EXPIRATION_DAYS:
            continue
        years = max(days / 365.0, MIN_TIME_YEARS)
        expirations_used += 1
        for is_call, frame in ((True, calls), (False, puts)):
            for row in frame.itertuples(index=False):
                oi = getattr(row, "openInterest", None)
                iv = getattr(row, "impliedVolatility", None)
                strike = float(row.strike)
                if oi is None or pd.isna(oi) or oi <= 0:
                    continue
                if iv is None or pd.isna(iv) or iv < IV_FLOOR:
                    continue
                gamma = black_scholes_gamma(spot, strike, years, float(iv))
                exposure = (
                    float(oi)
                    * CONTRACT_MULTIPLIER
                    * gamma
                    * spot
                    * spot
                    * 0.01
                )
                if is_call:
                    call_by_strike[strike] = (
                        call_by_strike.get(strike, 0.0) + exposure
                    )
                    per_strike[strike] = per_strike.get(strike, 0.0) + exposure
                else:
                    put_by_strike[strike] = (
                        put_by_strike.get(strike, 0.0) + exposure
                    )
                    per_strike[strike] = per_strike.get(strike, 0.0) - exposure

    if expirations_used == 0 or not per_strike:
        raise DataSourceError(
            f"{ticker}: sin datos de opciones utilizables dentro de "
            f"{MAX_EXPIRATION_DAYS} días"
        )

    call_gex = sum(call_by_strike.values())
    put_gex = -sum(put_by_strike.values())
    call_wall = (
        max(call_by_strike, key=call_by_strike.get) if call_by_strike else None
    )
    put_wall = (
        max(put_by_strike, key=put_by_strike.get) if put_by_strike else None
    )

    # Gamma flip: strike donde el GEX neto acumulado (de strike bajo a
    # alto) cambia de signo por primera vez alrededor del spot.
    gamma_flip: float | None = None
    cumulative = 0.0
    previous_sign = 0
    for strike in sorted(per_strike):
        cumulative += per_strike[strike]
        sign = 1 if cumulative > 0 else (-1 if cumulative < 0 else 0)
        if previous_sign != 0 and sign != 0 and sign != previous_sign:
            gamma_flip = strike
            break
        previous_sign = sign or previous_sign

    return GexProfile(
        ticker=ticker,
        spot=spot,
        call_gex=call_gex,
        put_gex=put_gex,
        net_gex=call_gex + put_gex,
        call_wall=call_wall,
        put_wall=put_wall,
        gamma_flip=gamma_flip,
        expirations_used=expirations_used,
    )


class GexEngine:
    name: ClassVar[EngineName] = EngineName.GEX
    version: ClassVar[str] = "1.0-bs-naive-dealer"

    def score_ticker(
        self,
        ticker: str,
        spot: float,
        chains: Mapping[str, tuple[pd.DataFrame, pd.DataFrame]],
        as_of: date,
    ) -> tuple[EngineResult, GexProfile]:
        profile = compute_gex_profile(ticker, spot, chains, as_of)
        score = max(-1.0, min(1.0, profile.normalized_balance))

        def strike_text(value: float | None) -> str:
            return f"{value:.0f}" if value is not None else "n/d"

        justification = (
            f"[{self.version}] GEX neto {profile.net_gex / 1e6:+,.0f}M USD/1% "
            f"(calls {profile.call_gex / 1e6:+,.0f}M, puts "
            f"{profile.put_gex / 1e6:+,.0f}M); call wall "
            f"{strike_text(profile.call_wall)}, put wall "
            f"{strike_text(profile.put_wall)}, gamma flip "
            f"{strike_text(profile.gamma_flip)}; spot {spot:.2f}; "
            f"{profile.expirations_used} vencimientos <= "
            f"{MAX_EXPIRATION_DAYS}d"
        )
        result = EngineResult(
            engine=self.name,
            ticker=ticker,
            score=score,
            justification=justification,
            data_source=DATA_SOURCE,
        )
        return result, profile
