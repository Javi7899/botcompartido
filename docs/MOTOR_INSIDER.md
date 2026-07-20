# Motor Insider (Fase 3.5) — diseño y validación en vivo

Motor 5 de la tabla 0.0. **Live-only** (Enmienda v1.2): el histórico masivo
de Form 4 point-in-time es inviable con fuentes gratuitas, así que se
valida en paper trading con el tratamiento de la sección 0.1 (peso inicial
conservador, persistencia diaria de predicciones).

## Fuente de datos: SEC EDGAR (`quantbot/data/edgar.py`)

- Mapa ticker→CIK desde `company_tickers.json`, submissions recientes desde
  `data.sec.gov`, y parsing del XML de cada Form 4.
- **User-Agent obligatorio:** la SEC devuelve HTTP 403 sin un contacto real
  en el User-Agent (formato "nombre contacto email"). Configurable vía
  `QUANTBOT_SEC_USER_AGENT` (fallo ruidoso con placeholder por defecto).
- Cortesía: delay de 0.15 s entre peticiones (la SEC permite 10 req/s;
  quedamos muy por debajo).
- Delay de reporte: el Form 4 se presenta hasta 2 días hábiles después de
  la transacción; el motor razona sobre la fecha de transacción, no la de
  filing, y solo puede ver filings ya presentados (sin look-ahead).

## Diseño (`quantbot/engines/insider.py`, v1.0-form4-weighted)

- Ventana: transacciones de los últimos 90 días naturales.
- **Solo mercado abierto:** códigos P (compra) y S (venta). Se excluyen M
  (ejercicio de opciones), F (retención fiscal), G (regalos), A (grants),
  etc., y **cualquier transacción bajo plan Rule 10b5-1** (rutinaria, no es
  señal — spec 2.1.5).
- Señal por transacción: valor en dólares × peso de rol × decaimiento por
  antigüedad (semivida 30 días). Las **ventas pesan 0.25×** (se vende por
  mil motivos, se compra por uno).
- Roles (spec: seniority pondera): CEO/CFO 1.0 · otros officers 0.7 ·
  directores / 10%-owners 0.5 · resto 0.3.
- Score = tanh(neto ponderado / 2M USD). Sin transacciones relevantes → 0
  (ausencia de actividad = información neutra, no dato faltante).

## Validación en vivo (2026-07-20)

`scripts/score_insider_universe.py` sobre 6 tickers: **funciona y captura
una realidad importante de las mega caps** — los insiders casi nunca
compran en mercado abierto; casi siempre venden (reciben acciones por
compensación y las liquidan, muchas veces vía 10b5-1). Resultados:

| Ticker | Score | Lectura |
|---|---|---|
| NVDA | −1.00 | 6 ventas, neto −20.6M USD ponderado |
| AAPL | −0.79 | 3 ventas, neto −2.1M USD |
| MSFT | −0.38 | 4 ventas, neto −0.8M USD |
| INTC | −0.12 | 2 ventas pequeñas |
| JPM | 0.00 | 17 transacciones, todas 10b5-1/opciones → descartadas |
| XOM | 0.00 | sin Form 4 en la ventana |

## Limitación conocida (para el ponderador bayesiano)

En mega caps el motor tenderá a señales negativas o neutras: su valor real
está en detectar la señal **rara y fuerte** de una compra en mercado
abierto de un alto directivo (evento poco frecuente pero históricamente
informativo). El filtro de 10b5-1 es esencial: sin él, JPM habría dado una
señal falsa a partir de ventas puramente rutinarias. Su capacidad
predictiva se medirá en paper trading.
