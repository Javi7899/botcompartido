# Backtest walk-forward — Motor Series Temporales (Fase 3.3)

Ejecutado el 2026-07-18 sobre el universo congelado (35 tickers, yfinance
desde 2012-01-01). Protocolo idéntico al del motor Técnico
(quantbot/backtest/runner.py): horizonte 21 sesiones no solapado, IC de
Spearman transversal, holdout desde 2022-01-01, criterio pre-registrado
PASA t≥2 / MARGINAL 1-2 / FALLA <1.

## Ronda 1 — v1: AR(5) OLS sobre retornos log (ventana 500)

| Periodo | Fechas | IC medio | IC std | t-stat | % IC>0 | Spread L-S (21d) |
|---|---|---|---|---|---|---|
| desarrollo (< 2022) | 108 | +0.0548 | 0.2969 | +1.92 | 53% | +0.0037 |
| holdout (≥ 2022) | 53 | +0.0245 | 0.2525 | +0.71 | 53% | +0.0027 |

**Veredicto v1: FALLA** (t holdout 0.71).

## Protocolo de simplificación (solo desarrollo, holdout intacto)

`scripts/analyze_timeseries_variants.py`, exclusivamente 2012-2021:

| Variante | IC medio (dev) | t-stat (dev) | % IC>0 | Spread L-S |
|---|---|---|---|---|
| AR(1) | +0.0684 | +2.40 | 61% | +0.0059 |
| AR(2) | +0.0669 | +2.35 | 58% | +0.0060 |
| AR(5) [original] | +0.0613 | +2.18 | 53% | +0.0051 |
| Solo deriva (media 500d) | +0.0671 | +2.36 | 59% | +0.0066 |

Decisión (solo con desarrollo): **AR(1)** — la más simple y la de mayor
evidencia. (La deriva pura empataba, pero solapa conceptualmente con el
motor Técnico de tendencia; AR(1) aporta dinámica propia.)

## Ronda 2 — v2 AR(1): confirmación one-shot en holdout

| Periodo | Fechas | IC medio | IC std | t-stat | % IC>0 | Spread L-S (21d) |
|---|---|---|---|---|---|---|
| desarrollo (< 2022) | 108 | +0.0616 | 0.3025 | +2.11 | 60% | +0.0045 |
| holdout (≥ 2022) | 53 | +0.0074 | 0.2676 | +0.20 | 47% | −0.0023 |

## Veredicto final: FALLA — MOTOR DESCARTADO de la Fase 4

La autocorrelación diaria que sostenía el motor en 2012-2021 (t=2.11 en
desarrollo) **no existe en 2022-2026** (t=0.20, spread L-S negativo, IC
positivo solo el 47% de los meses). Interpretación directa: la señal fue
arbitrada; un proceso ingenuo que solo mirara el desarrollo la habría
integrado con confianza — este es exactamente el caso que el corte
out-of-sample existe para cazar.

Consecuencias registradas:

1. **El motor NO se integra en la ponderación bayesiana de Fase 4**
   (peso prior = 0).
2. El código se conserva y sus predicciones diarias se seguirán
   persistiendo (coste cero) para que el paper trading acumule evidencia
   fresca; solo una evidencia nueva y significativa reabriría su
   integración, como decisión explícita nueva.
3. El holdout se consultó dos veces (AR(5) y AR(1)); queda cerrado para
   este motor — no habrá más iteraciones de diseño sobre estos datos.

## Nota de proceso

La regla del spec ("no ajustar hasta que funcione") se cumplió: la única
iteración permitida fue la simplificación elegida con datos de desarrollo,
y su confirmación consumió el disparo final. El resultado negativo queda
documentado con el mismo detalle que un positivo — un motor descartado a
tiempo es una victoria del proceso, no un fracaso.
