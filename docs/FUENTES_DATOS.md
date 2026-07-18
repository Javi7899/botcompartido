# Fuentes de datos (Fase 2) — decisiones y limitaciones

Validado en vivo el 2026-07-18 con `scripts/validate_data_sources.py`.
Este documento registra qué fuente alimenta cada motor, sus limitaciones
conocidas y las decisiones de limpieza tomadas en Fase 2.

## OHLCV — yfinance

- **Qué se guarda** (`daily_bars`): precios **sin ajustar** (open/high/low/close
  tal como cotizaron), más `adj_close`, dividendo del día y ratio de split.
  Los motores estadísticos (Técnico, Series Temporales, XGBoost) usan
  `adj_close` para series de retorno total; todo lo que razona sobre precios
  reales negociados (comisiones, redondeo a acciones enteras) usa `close`.
- **Deriva del adj_close:** yfinance recalcula toda la serie ajustada tras
  cada dividendo nuevo. Por eso `store_bars` tolera diferencias solo en
  `adj_close` al re-ingerir; una diferencia en los precios crudos o el
  volumen lanza excepción (la fuente reescribió la historia → decisión
  humana). Implicación: para backtests largos, el ajuste se recalcula desde
  dividendos/splits crudos o se refresca la serie completa (decisión de
  Fase 3 documentada aquí para no olvidarla).
- **Validación en vivo:** 251 barras/año por ticker, sin NaN, columna
  `Adj Close` presente con `auto_adjust=False, actions=True`.
- **Cross-validación (2026-07-18):** closes de yfinance contrastados contra
  la API histórica pública de Nasdaq (últimas ~20 sesiones, tolerancia 1%):
  AAPL, KO y JPM sin desviaciones. Stooq se descartó como referencia por
  estar detrás de un challenge JavaScript anti-bot. El VIX de FRED coincide
  exactamente con el ^VIX de Yahoo en la última fecha compartida.

## Macro — FRED (`fredgraph.csv`, sin API key)

- Series elegidas (`DEFAULT_SERIES`): DGS10, DFF, T10Y2Y, CPIAUCSL, UNRATE,
  VIXCLS. Diarias o mensuales, histórico profundo (DGS10 desde 1962).
- **Valores faltantes:** FRED usa `"."` **y también cadena vacía** `""`
  (hallazgo de la validación en vivo). Ambos se omiten y se cuentan.
- **Revisiones:** FRED revisa series como CPI. Una re-ingesta con valor
  distinto al almacenado lanza excepción — las revisiones se tratan
  manualmente para no corromper la reproducibilidad del backtest.
- **Look-ahead:** las series mensuales (CPI, UNRATE) se publican con retraso;
  el motor macro (Fase 3.7) debe usar la fecha de *publicación*, no la fecha
  de referencia de la observación. Pendiente de resolver en Fase 3 (ALFRED
  ofrece vintages point-in-time si hace falta).

## Noticias — RSS con timestamp exacto

- **Feeds:** Yahoo Finance por ticker (`yahoo_ticker_rss`), Yahoo mercado,
  CNBC top news y notas de prensa de la Reserva Federal. Todos validados.
- **Archivo point-in-time (`news_items`, append-only):** cada noticia se
  guarda con su timestamp de publicación Y el de descarga. Este archivo
  empieza a acumularse desde Fase 2 precisamente porque no existe histórico
  gratuito de noticias con timestamp (spec 0.1) — cada día que corre el
  pipeline construye el dataset que el motor de Noticias necesitará.
- **Entradas sin timestamp:** se descartan con aviso en el log. Una noticia
  sin fecha exacta es inutilizable bajo la disciplina point-in-time.

## Opciones — yfinance, subconjunto GEX

- **Validación estructural (nivel 2.1.6-1):** los 7 tickers de `GEX_SUBSET`
  (AAPL, AMZN, GOOGL, META, MSFT, NVDA, TSLA) y SPY como referencia pasaron
  todos: OI total 100k-700k por ticker, 0% de IV ausente, strikes rodeando
  el spot, 4 vencimientos próximos.
- **Cross-validación automática (nivel 2.1.6-1, CERRADA el 2026-07-18):**
  `scripts/cross_validate_sources.py` compara yfinance contra el JSON
  público de CBOE (cdn.cboe.com). Resultado: OI por vencimiento coincide
  casi al contrato exacto (ej. NVDA 430.972 vs 430.974; SPY 263.372 vs
  263.425) e IV ATM a ≥14 días dentro del 6% (SPY exacta: 0.155 = 0.155).
  La IV de vencimientos sub-semanales NO es comparable entre proveedores
  (dominada por el timing del snapshot) — por eso la comparación usa el
  primer vencimiento con ≥14 días de vida.
- **Limitación conocida:** el OI de yfinance es de cierre de T-1, coherente
  con la arquitectura general, con la limitación de gap intersesión ya
  documentada en el spec 2.1.6.

## Fundamentales — conclusión point-in-time (spec 1.1)

**Los fundamentales de yfinance NO son point-in-time.** Devuelven la foto
actual (valores ya revisados/restated), no el dato tal como se conocía en
cada fecha histórica. Conclusión de Fase 2, alineada con el spec 0.1:

1. Está **prohibido** backtestear el motor Fundamental con los datos
   snapshot de yfinance como si fueran históricos.
2. El motor Fundamental (Fase 3.2) opera solo en vivo: sus predicciones se
   persisten a diario y su validación real es el paper trading (Fase 8).
3. Su peso bayesiano inicial es conservador hasta acumular evidencia.
