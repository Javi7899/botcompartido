# Bot Cuantitativo Compartido

Bot de trading cuantitativo para una cuenta de 5.000€ en Interactive Brokers Pro (comisiones Fija), construido de forma estrictamente modular y por fases.

**Arquitectura completa y fuente de verdad:** [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)

## Resumen del sistema

- **Universo:** 30-40 blue chips de EEUU (S&P 500); cartera concentrada en máx. 10-20 posiciones.
- **Cadencia:** una ejecución diaria → señales con datos T-1 → órdenes MOC al cierre de la sesión en curso.
- **Cerebro en 3 capas:** 7 motores de señal → ponderador bayesiano jerárquico (global → por activo con shrinkage) → supervisor LLM con poder de veto.
- **Cartera:** Black-Litterman + Kelly fraccionario + filtro estricto de comisiones.
- **Infraestructura:** Python, pydantic, SQLAlchemy/SQLite (trazabilidad inmutable), Loguru, `ib_insync`/`ib_async`.

## Estado actual

**Fase 3 en curso (motor Técnico).** Fase 2 cerrada con cross-validación automática contra fuentes independientes (CBOE, Nasdaq, Yahoo): ver [docs/FUENTES_DATOS.md](docs/FUENTES_DATOS.md).

| Fase | Descripción | Estado |
|---|---|---|
| 1 | Infraestructura y Base de Datos | Completada |
| 2 | Ingesta de Datos y Limpieza | Completada |
| 3 | Desarrollo Motor a Motor (7 motores) | **Completada — 7 de 7** |
| 4 | Meta-Modelo Bayesiano y Correlaciones | [Completada](docs/FASE4_META_MODELO.md) |
| 5 | Supervisor IA | [Completada](docs/FASE5_SUPERVISOR.md) |
| 6 | Optimización de Cartera | [Completada](docs/FASE6_CARTERA.md) |
| 7 | Ejecución MOC (IBKR) | Pendiente |
| 8 | Paper Trading (mín. 6 meses) | Pendiente |
| 9 | Capital Real | Pendiente |

### Estado de los motores (Fase 3)

| # | Motor | Veredicto | Integración en Fase 4 |
|---|---|---|---|
| 1 | Técnico | [MARGINAL](docs/BACKTEST_MOTOR_TECNICO.md) — v2 tendencia SMA200 | Sí, peso inicial bajo |
| 2 | Fundamental | [Live-only](docs/MOTOR_FUNDAMENTAL.md) — sin backtest posible | Sí, peso conservador |
| 3 | Series Temporales | [FALLA](docs/BACKTEST_MOTOR_SERIES_TEMPORALES.md) — descartado | No |
| 4 | ML (XGBoost/Ridge) | [FALLA](docs/BACKTEST_MOTOR_ML.md) — descartado | No |
| 5 | Insider Trading | [Live-only](docs/MOTOR_INSIDER.md) — Form 4/EDGAR | Sí, peso conservador |
| 6 | GEX | [Live-only](docs/MOTOR_GEX.md) — gamma Black-Scholes | Sí, peso conservador |
| 7 | Macro/Noticias | [Live-only](docs/MOTOR_NOTICIAS.md) — léxico financiero | Sí, peso conservador |

Lección de la Fase 3: los 3 motores de precio backtesteables (Técnico, Series Temporales, ML) mostraron señal en 2012-2021 y degradación en 2022-2026; solo el Técnico sobrevivió, marginalmente. El sistema se apoyará en los motores de información no-precio (Insider, GEX, Noticias, Fundamental) y en la gestión de cartera.

## Reglas de desarrollo

1. Solo se implementa lo que corresponde a la fase actual.
2. No se avanza de fase sin backtest walk-forward validado y aprobación explícita.
3. Lo que no muestre mejora significativa out-of-sample se simplifica o se descarta.
