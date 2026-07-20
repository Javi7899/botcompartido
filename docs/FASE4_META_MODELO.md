# Fase 4 — Meta-Modelo Bayesiano Jerárquico y Correlaciones

Implementa la Capa 2.2 del spec con el diseño de la Enmienda 2 (ponderador
jerárquico con shrinkage). Ejecutado el 2026-07-20.

## Objetivo (Enmienda 2)

Que un motor pese más en los activos donde predice mejor (técnico en NVDA,
fundamental en otro) **sin** los ~250 parámetros libres de un ponderador
por-activo puro. El mecanismo es shrinkage sobre el information coefficient
(IC): el peso por activo parte del peso global del motor y se desvía en
proporción a la evidencia acumulada de ese activo.

## Mecánica (`quantbot/meta/bayesian.py`)

1. **IC por motor** = correlación de Spearman entre el score del motor y el
   retorno forward. Se calcula global (todos los pares agrupados) y por
   activo. Menos de 12 observaciones → IC no fiable (se usa el prior).
2. **IC global shrunk hacia un prior**: `shrink(sample, n, prior, k)` =
   media ponderada por precisión. El prior vale `prior_strength=100`
   pseudo-observaciones. Los motores **live-only** (fundamental, insider,
   gex, noticias) no tienen evidencia histórica, así que se quedan en su
   prior conservador (`prior_ic=0.01`) hasta que el paper trading acumule
   observaciones (spec 0.1).
3. **IC por activo shrunk hacia el global** con `asset_shrinkage=75`
   pseudo-obs: pocas observaciones del activo → peso ≈ global; muchas →
   se acerca al IC propio del activo.
4. **Peso = max(0, IC shrunk)**, normalizado por activo entre los motores
   que aplican. GEX e Insider se **excluyen** (no se imputan neutros) en
   los activos sin dato — GEX solo en el subconjunto líquido.

## Resultado inicial (solo Técnico con evidencia; resto en prior)

Antes de la Fase 8 solo el motor Técnico tiene evidencia histórica (su
holdout 2022+ del walk-forward de Fase 3). IC global tras shrinkage:

| Motor | IC global | Origen |
|---|---|---|
| technical | +0.0073 | evidencia holdout (pooled, ~53 obs/activo) |
| fundamental | +0.0100 | prior conservador (live-only) |
| insider | +0.0100 | prior conservador (live-only) |
| gex | +0.0100 | prior conservador (live-only) |
| macro_news | +0.0100 | prior conservador (live-only) |

Pesos por activo (muestra), donde se ve la diferenciación buscada:

| Activo | Pesos |
|---|---|
| NVDA | technical 0.61, resto 0.10 c/u |
| AAPL | technical 0.00 → fundamental/insider/gex/noticias 0.25 c/u |
| KO | fundamental/insider/noticias 0.33 (GEX excluido: sin opciones líquidas) |
| JPM | fundamental/insider/noticias 0.33 (GEX excluido) |

El Técnico pesa 0.61 en NVDA (buen IC por-activo en el holdout) y 0 en AAPL
(su IC por-activo no supera el ruido) — exactamente la diferenciación por
activo que el spec pedía, gobernada por la evidencia y no por 250
parámetros libres.

## Nota honesta sobre la evidencia por activo

El IC por-activo del Técnico se estima con solo ~53 observaciones (una cada
21 sesiones desde 2022). Es poca evidencia, y por eso el shrinkage hacia el
global (bajo) es esencial: modera pesos por-activo que de otro modo serían
ruido. Estos pesos son un **punto de partida**, no una verdad final — su
razón de ser es refinarse con el paper trading (Fase 8), donde cada motor,
incluidos los live-only, acumula observaciones reales. El IC pooled del
Técnico (+0.0073) es más bajo que su IC transversal del backtest (+0.031)
porque la señal técnica es sobre todo de ranking transversal, no de timing
temporal por activo — un matiz que el ponderador captura correctamente.

## Correlaciones (`quantbot/meta/correlations.py`)

Matriz de correlación de retornos log entre activos, con clusters de factor
(|corr| ≥ 0.7). El resultado valida el enfoque — detecta exactamente los
factores sectoriales que el optimizador (Fase 6) debe evitar sobre-
concentrar:

- Bancos: JPM ↔ BAC ↔ WFC
- Petroleras: XOM ↔ CVX
- Bebidas: KO ↔ PEP
- Redes de pago: V ↔ MA

## Persistencia

`scripts/build_bayesian_weights.py` persiste los pesos globales
(`ticker=NULL`) y por activo en la tabla `bayesian_weights` (append-only),
con `evidence_count` para trazar cuánta evidencia sostiene cada peso.
