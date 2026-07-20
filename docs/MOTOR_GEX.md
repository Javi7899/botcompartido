# Motor GEX (Fase 3.6) — diseño y validación en vivo

Motor 6 de la tabla 0.0. **Live-only** (Enmienda v1.2): las cadenas de
opciones históricas (OI/IV por día) no existen en fuentes gratuitas, así
que el backtest histórico es imposible por construcción. Se valida en paper
trading con el tratamiento de la sección 0.1.

## Diseño (`quantbot/engines/gex.py`, v1.0-bs-naive-dealer)

- Subconjunto GEX (7 tickers de opciones líquidas) + SPY como referencia.
- Gamma vía **Black-Scholes** (idéntica para calls y puts); r=0.04 fijo (la
  gamma es casi insensible al tipo). Vencimientos ≤ 45 días.
- GEX por strike = OI × 100 × gamma × spot² × 0.01 (USD por movimiento de
  1%), con **calls en positivo y puts en negativo** (ver convención abajo).
- Perfil agregado: GEX neto, call wall (strike con más GEX de calls), put
  wall, gamma flip (strike donde el GEX neto acumulado cruza cero).
- Score = balance normalizado (call_gex − |put_gex|) / (call_gex +
  |put_gex|) ∈ [−1, 1]. Es una señal de **régimen** (gamma + = pinning /
  estabilidad; gamma − = aceleración), no direccional.

## Convención de signo (CORREGIDA en Enmienda v1.2)

La v1.1 del spec asumía dealers cortos de calls / largos de puts. La
convención estándar de las herramientas públicas (SqueezeMetrics y
similares) — contra las que el propio spec exige comparar en el nivel 3 de
validación — es la **contraria**: dealers largos de calls (gamma +) y
cortos de puts (gamma −). Se corrigió en el código y en el spec 2.1.6 para
que la comparación de signos sea válida.

## Validaciones del spec 2.1.6

1. **Fuente de datos:** cubierta en Fase 2 (cross-validación de OI/IV vs
   CBOE; ver docs/FUENTES_DATOS.md).
2. **Caso manual (test unitario):** `test_gex.py` reproduce a mano la gamma
   Black-Scholes (S=K=100, T=30/365, σ=0.20 → γ=0.06931) y la fórmula GEX
   por strike (1000 calls ATM → 693.110 USD/1%).
3. **Validación cruzada de niveles:** `scripts/score_gex_subset.py` imprime
   walls, gamma flip y signo del régimen para comparar contra herramientas
   públicas de gamma exposure.
4. **Consistencia temporal:** el gamma flip y los walls no deben saltar sin
   causa (movimiento grande o vencimiento); se vigila en paper trading.

## Validación en vivo (2026-07-20)

`scripts/score_gex_subset.py`, resultados coherentes con la teoría:

| Ticker | Score | GEX neto | Lectura |
|---|---|---|---|
| SPY | −0.38 | −6.667M/1% | gamma negativa (puts de hedging dominan, típico de índices) |
| MSFT | +0.61 | +375M/1% | gamma positiva fuerte (pinning) |
| META | +0.49 | +348M/1% | pinning, call wall = put wall en 650 |
| AMZN | +0.41 | +167M/1% | régimen estable |
| GOOGL | +0.25 | +72M/1% | ligeramente positivo |
| NVDA | +0.15 | +158M/1% | equilibrado |
| AAPL | −0.17 | −171M/1% | ligera gamma negativa |
| TSLA | −0.20 | −98M/1% | gamma negativa (aceleración) |

Los walls caen pegados al spot en todos los casos y el signo negativo de
SPY (donde los inversores compran protección masivamente) valida que la
convención corregida es la correcta.

## Limitación conocida (spec 2.1.6)

OI de T-1 con spot de T: un gap intersesión grande desplaza el spot fuera
de la zona de strikes donde el OI de T-1 es representativo. Documentado; su
impacto real se observará en paper trading.
