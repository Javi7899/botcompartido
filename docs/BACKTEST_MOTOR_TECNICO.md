# Backtest walk-forward — Motor Técnico (Fase 3.1)

Ejecutado el 2026-07-18 sobre el universo congelado (35 tickers, yfinance
desde 2012-01-01). Este documento registra el proceso COMPLETO, incluido el
fallo de la primera versión — la trazabilidad del proceso de decisión es
parte del gate de fase.

## Metodología

- Horizonte de evaluación: 21 sesiones, fechas no solapadas (161 fechas).
- Score calculado solo con datos hasta t (T-1 estricto); retorno forward =
  adj_close[t+21]/adj_close[t] − 1.
- IC = correlación de Spearman transversal (score vs retorno forward) por
  fecha; spread L-S = tercil superior − tercil inferior.
- Sin parámetros ajustados en ninguna versión del motor; el corte
  2022-01-01 separa desarrollo de holdout para proteger contra el sesgo de
  diseño (el motor se diseñó conociendo la historia hasta hoy).

## Criterio pre-registrado (fijado antes de ver resultados)

- **PASA**: t-stat del IC medio en holdout ≥ 2.0.
- **MARGINAL**: t-stat en [1.0, 2.0) — se mantiene con peso bayesiano
  inicial bajo.
- **FALLA**: t-stat < 1.0 — se simplifica o descarta (regla 3 del spec).

## Ronda 1 — v1 compuesto (tendencia + momentum 12-1 + reversión RSI14)

| Periodo | Fechas | IC medio | IC std | t-stat | % IC>0 | Spread L-S (21d) |
|---|---|---|---|---|---|---|
| desarrollo (< 2022) | 108 | +0.0116 | 0.2599 | +0.46 | 54% | +0.0018 |
| holdout (≥ 2022) | 53 | +0.0344 | 0.2546 | +0.98 | 60% | +0.0059 |

**Veredicto v1: FALLA** (t holdout 0.98 < 1.0).

## Protocolo de simplificación (sin contaminar el holdout)

Análisis por componentes **exclusivamente en desarrollo** (2012-2021,
`scripts/analyze_technical_components.py`); el holdout quedó intacto:

| Variante | IC medio (dev) | t-stat (dev) | % IC>0 | Spread L-S |
|---|---|---|---|---|
| Solo tendencia (SMA200) | +0.0266 | +1.01 | 57% | +0.0054 |
| Solo momentum 12-1 | +0.0278 | +1.01 | 54% | +0.0023 |
| Solo reversión RSI14 | −0.0074 | −0.31 | 46% | −0.0012 |
| Tendencia + momentum | +0.0205 | +0.75 | 55% | +0.0029 |

Conclusiones del desarrollo: la reversión RSI es ruido dañino que diluía el
compuesto; tendencia y momentum empatan en IC pero la tendencia dobla el
spread económico. **Decisión (tomada solo con datos de desarrollo):
simplificar a tendencia pura** — score = tanh(5 × (close/SMA200 − 1)).

## Ronda 2 — v2 tendencia pura: confirmación one-shot en holdout

| Periodo | Fechas | IC medio | IC std | t-stat | % IC>0 | Spread L-S (21d) |
|---|---|---|---|---|---|---|
| desarrollo (< 2022) | 108 | +0.0246 | 0.2724 | +0.94 | 56% | +0.0051 |
| holdout (≥ 2022) | 53 | +0.0307 | 0.2170 | +1.03 | 58% | +0.0035 |

## Veredicto final: MARGINAL

El motor Técnico v2 (`2.0-trend-only`) queda **aprobado con evidencia
débil**: IC positivo y consistente en ambos periodos (t≈1 en cada uno),
spread L-S positivo, pero por debajo del umbral de significación fuerte.
Consecuencias registradas:

1. Se integra en la Fase 4 con **peso bayesiano inicial bajo**
   (evidence_count refleja las 161 observaciones y su t-stat).
2. Sus predicciones diarias se persisten desde el primer día para que el
   paper trading (Fase 8) acumule evidencia adicional.
3. No se harán más iteraciones de diseño sobre estos mismos datos: el
   holdout ya se consultó dos veces (compuesto + confirmación) y una
   tercera lo convertiría en muestra de desarrollo (overfitting).

## Lección honesta

Con 35 mega caps y horizonte mensual, las señales técnicas clásicas tienen
poder predictivo real pero pequeño. Es lo esperable en activos tan
eficientes con una sección cruzada tan corta — y es exactamente la razón
por la que el sistema combina 7 motores con ponderación por evidencia en
lugar de confiar en uno solo.
