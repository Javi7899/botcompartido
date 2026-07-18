# Backtest walk-forward — Motor ML (Fase 3.4)

Ejecutado el 2026-07-18 sobre el universo congelado (35 tickers, yfinance
desde 2012-01-01). Protocolo estándar (quantbot/backtest/runner.py) con la
particularidad de que aquí el modelo SÍ se entrena: reentrenamiento
expansivo cada 126 sesiones con **embargo de 21** (ninguna etiqueta de
entrenamiento usa información posterior a la fecha de predicción; el
embargo está verificado con test unitario mediante un modelo espía).

## Diseño común a todas las rondas

- 10 features OHLCV T-1: ret_5d, ret_21d, ret_63d, mom_12_1, vol_21d,
  vol_63d, dist_52w_high, dist_52w_low, sma200_ratio, volume_ratio.
- Target: retorno forward 21d **demeaned transversalmente** (rendimiento
  relativo entre pares, no dirección del mercado).
- Nada se tuneó contra el backtest: hiperparámetros fijados a priori.

## Ronda 1 — v1: XGBoost (200 rondas, depth 3, mcw 50, eta 0.05)

| Periodo | Fechas | IC medio | IC std | t-stat | % IC>0 | Spread L-S (21d) |
|---|---|---|---|---|---|---|
| desarrollo (< 2022) | 93 | +0.0408 | 0.2060 | +1.91 | 56% | +0.0070 |
| holdout (≥ 2022) | 53 | +0.0119 | 0.2249 | +0.39 | 51% | +0.0067 |

**Veredicto v1: FALLA** (t holdout 0.39).

## Protocolo de simplificación (solo desarrollo, holdout intacto)

`scripts/analyze_ml_variants.py`, exclusivamente 2012-2021, con solo DOS
candidatos para limitar los caminos de decisión:

| Variante | IC medio (dev) | t-stat (dev) | % IC>0 | Spread L-S |
|---|---|---|---|---|
| XGBoost v1 [referencia] | +0.0409 | +1.90 | 55% | +0.0074 |
| **Ridge lineal (λ=10)** | **+0.0822** | **+3.30** | **65%** | **+0.0134** |
| XGBoost extra-reg | +0.0328 | +1.51 | 57% | +0.0067 |

Hallazgo clásico de ML financiero: con relación señal/ruido tan baja, el
modelo lineal domina a los árboles (que encuentran estructura espuria
incluso fuertemente regularizados). Decisión (solo desarrollo): **Ridge**.

## Ronda 2 — v2 Ridge: confirmación one-shot en holdout

| Periodo | Fechas | IC medio | IC std | t-stat | % IC>0 | Spread L-S (21d) |
|---|---|---|---|---|---|---|
| desarrollo (< 2022) | 93 | +0.0785 | 0.2403 | +3.15 | 65% | +0.0126 |
| holdout (≥ 2022) | 53 | +0.0262 | 0.2580 | +0.74 | 53% | +0.0087 |

## Veredicto final: FALLA — MOTOR DESCARTADO de la Fase 4

Un t de 3.15 en desarrollo se queda en 0.74 fuera de muestra. El IC del
holdout es positivo (+0.026) y el spread económico no es despreciable
(+0.87%/21d), pero el criterio pre-registrado es t≥1 y no se alcanza.
Consecuencias registradas:

1. **NO se integra en la ponderación bayesiana de Fase 4** (peso prior 0).
2. Código y features se conservan; sus predicciones diarias se seguirán
   persistiendo para que el paper trading acumule evidencia fresca.
3. El holdout se consultó dos veces (XGBoost y Ridge): queda **cerrado**
   para este motor. No habrá tercera iteración sobre estos datos.

## Patrón transversal que ya no se puede ignorar

Tres motores de precio evaluados (Técnico, Series Temporales, ML) y el
mismo dibujo en los tres: señal aparente en 2012-2021, degradación severa
en 2022-2026. La lectura honesta es que las señales transversales de
precio en mega caps se han arbitrado en el periodo reciente. Implicación
para el proyecto: el peso del sistema recaerá más en los motores de
información no-precio (Insider, GEX, Noticias, Fundamental) y en la
gestión de cartera (Black-Litterman + Kelly + filtro de comisiones) que
en la predicción de retornos por precio. Esta constatación empírica,
comprada con backtests disciplinados y no con dinero real, es
exactamente el retorno de inversión de la Fase 3.
