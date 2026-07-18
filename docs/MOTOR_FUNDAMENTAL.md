# Motor Fundamental (Fase 3.2) — diseño y validación en vivo

Motor 2 de la tabla 0.0. **Live-only**: la conclusión de Fase 2
(docs/FUENTES_DATOS.md) es que los fundamentales de yfinance no son
point-in-time, así que el backtest histórico está prohibido para este
motor. Su validación real será el paper trading (Fase 8), tratándose desde
el día 1 según las reglas de la sección 0.1 del spec:

1. Peso bayesiano inicial conservador (inferior al de los motores con
   backtest).
2. Cada predicción diaria se persiste con su justificación completa para
   evaluación acumulativa.
3. Vigilancia específica del look-ahead antes de subirle el peso o pasar
   a Fase 9.

## Diseño (`quantbot/engines/fundamental.py`, v1.0-cross-sectional-rank)

Score **transversal por ranking dentro del universo** — un fundamental
solo es bueno o malo relativo a los pares. Cuatro métricas de igual peso,
cada una convertida a percentil centrado [-1, +1] entre los tickers que la
publican:

| Métrica | Fuente (yfinance info) | Dirección |
|---|---|---|
| Earnings yield | 1 / trailingPE (solo si PE > 0) | Mayor = mejor |
| ROE | returnOnEquity | Mayor = mejor |
| Margen neto | profitMargins | Mayor = mejor |
| Crecimiento de ingresos | revenueGrowth | Mayor = mejor |

Reglas de robustez: un PE negativo (sin beneficios) deja la métrica
ausente en lugar de generar un yield absurdo; un ticker necesita ≥2
métricas para puntuar; si menos de 10 tickers son utilizables, el motor
falla ruidosamente (la fuente está rota). Se descartó deliberadamente el
apalancamiento (debtToEquity): con bancos en el universo (JPM, BAC, WFC)
esa métrica no es comparable entre sectores.

## Validación en vivo (2026-07-18)

`scripts/score_fundamental_universe.py`: **cobertura 35/35 tickers**, con
resultados coherentes de sanidad: INTC (ROE y márgenes negativos) al
fondo (−0.76), TSLA penalizada por valoración extrema (earnings yield
0.3%, rank −1.00), y las petroleras/defensivas caras y sin crecimiento en
la mitad inferior. Casos de manejo de ausencias verificados en real: INTC
sin trailingPE (pérdidas) puntúa con 3 métricas.

## Sin backtest — por diseño, no por olvido

Cualquier "backtest" con los datos snapshot actuales sería una mentira
metodológica (look-ahead masivo: los ratios de hoy incorporan revisiones
y restatements). La evidencia de este motor empezará a contarse el primer
día de pipeline diario y se evaluará con el histórico acumulado.
