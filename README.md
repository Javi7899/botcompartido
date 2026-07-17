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

**Pre-Fase 1.** Spec de arquitectura v1.1 acordado (con enmiendas). No hay código todavía.

| Fase | Descripción | Estado |
|---|---|---|
| 1 | Infraestructura y Base de Datos | Pendiente |
| 2 | Ingesta de Datos y Limpieza | Pendiente |
| 3 | Desarrollo Motor a Motor (7 motores) | Pendiente |
| 4 | Meta-Modelo Bayesiano y Correlaciones | Pendiente |
| 5 | Supervisor IA | Pendiente |
| 6 | Optimización de Cartera | Pendiente |
| 7 | Ejecución MOC (IBKR) | Pendiente |
| 8 | Paper Trading (mín. 6 meses) | Pendiente |
| 9 | Capital Real | Pendiente |

## Reglas de desarrollo

1. Solo se implementa lo que corresponde a la fase actual.
2. No se avanza de fase sin backtest walk-forward validado y aprobación explícita.
3. Lo que no muestre mejora significativa out-of-sample se simplifica o se descarta.
