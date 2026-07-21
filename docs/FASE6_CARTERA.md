# Fase 6 — Optimización de Cartera (Black-Litterman + Kelly + Comisiones)

Implementa la sección 3 del spec con las restricciones de la Enmienda 1
(cartera concentrada, acciones enteras) y la expectativa de la Enmienda 6
(baja rotación por el mínimo de comisión).

## Black-Litterman (`quantbot/portfolio/black_litterman.py`)

- **Prior de equilibrio**: π = δ Σ w_mercado (δ = 2.5, valor clásico).
- **Views como TILT sobre el prior**: q_i = π_i + escala · score_i.
  Este detalle es load-bearing: tratar un score de 0 como "view de que el
  retorno es 0" (el error habitual) arrastra el posterior hacia abajo y
  distorsiona todos los pesos. Con el tilt, score 0 = "sin opinión" y el
  posterior recupera exactamente los pesos de mercado (verificado en test).
- **Ω por He-Litterman**: Ω = diag(P τΣ Pᵀ) / confianza. Una Ω absoluta fija
  (p. ej. 0.02) queda aplastada por (τΣ)⁻¹ y los scores de los motores
  apenas moverían el posterior — se detectó midiendo que un score de −1.0
  dejaba el posterior en +0.043 (prácticamente el prior). Con He-Litterman,
  view y prior pesan igual a confianza 1.
- **Long-only** y normalizado. Si el posterior es negativo en todo el
  universo, la cartera queda vacía (todo cash).

## Kelly fraccionario (`kelly.py`)

BL fija los pesos **relativos**; Kelly fija la **exposición total** (cuánto
capital desplegar vs. mantener en cash), con fracción 0.35 (rango 0.25-0.50
del spec) y tope 1.0 (sin apalancamiento). Edge no positivo → exposición 0.

Esta separación de responsabilidades está verificada con test: views
moderadamente negativas e iguales **no** vacían la cartera en BL (los pesos
relativos no cambian) — reducir la exposición es trabajo de Kelly.

## Acciones enteras y nº de posiciones (`sizing.py`) — hallazgo de diseño

Las órdenes MOC de IBKR no admiten fracciones, así que los pesos se
convierten a acciones enteras. **El número de posiciones se deriva del
capital desplegable**, no es fijo:

```
n = min(max_positions, desplegable // min_position_usd)
```

Sin esto el sistema no funcionaba: Kelly despliega típicamente ~23% de los
$5.000 (≈$1.167); repartido entre 15 posiciones fijas da $78 cada una —
menos que el precio de una sola acción de casi cualquier blue chip. En la
primera ejecución de la simulación **todas las posiciones salían no
invertibles y se generaban cero órdenes**. Derivando el número (≈2-5
posiciones de $300-400) el sistema concentra el capital desplegable en las
mejores señales, que es justo lo que la Enmienda 1 pretendía.

Dividir por el mínimo tampoco basta por sí solo, porque el **redondeo** a
acciones enteras puede dejar la posición por debajo del mínimo aunque la
asignación lo supere (una asignación de $383 en un título de $200 compra 1
acción = $200 < $300). Por eso el número se reduce iterativamente hasta que
**todas** las posiciones seleccionadas son viables.

`round_to_shares` devuelve un `SizingResult` con dos listas: `positions`
(las que se compran, todas invertibles) y `excluded` (las descartadas con
el motivo exacto), preservando la trazabilidad de por qué cada candidato
quedó fuera.

## Filtro de Comisiones (`commissions.py`) — decisión del nivel de aplicación

Modelo IBKR Pro Fija: $0.005/acción, **mínimo $1**, tope 1% del valor.
Una orden solo se genera si (1) la desviación supera el umbral y (2) el
beneficio esperado ≥ 3× la comisión.

El spec exige decidir explícitamente el nivel de aplicación. Comparación
sobre precios reales del universo (2024-01 → 2026-07, rebalanceo mensual,
`scripts/compare_commission_filter.py`):

| Variante | Rebalanceos | Órdenes | Comisiones | Turnover | Com./capital |
|---|---|---|---|---|---|
| individual | 18 | 28 | $28.00 | $14.127 | 0.56% |
| aggregate | 18 | 28 | $28.00 | $14.127 | 0.56% |

**Decisión: INDIVIDUAL** (por defecto). Las dos variantes convergen porque
la cartera que impone la aritmética de $5.000 es tan concentrada (3-5
posiciones de $300-400) que cada ajuste ya supera el umbral por sí solo —
la distinción solo importaría con muchas posiciones pequeñas, que es
precisamente lo que la concentración evita. Ante el empate se elige la
variante más simple y conservadora: nunca ejecuta un ajuste que no se
justifique por sí mismo. `AGGREGATE` queda implementada y testeada por si
un cambio futuro de capital o de nº de posiciones la hace relevante.

**Coste confirmado:** 0.56% del capital en 2,5 años de comisiones, con 28
órdenes (≈11 al año). La baja rotación que anticipaba la Enmienda 6 se
cumple: el mínimo de $1 por orden es el 100% de la comisión pagada en cada
operación, y aun así el coste total queda por debajo del 0.6% del capital.

> La simulación mide **coste y frecuencia de operación, no rentabilidad**:
> los motores de precio ya fallaron su gate en Fase 3 y los scores usados
> aquí son sintéticos y deterministas. No es un backtest de resultados.

## Tests

**37 tests** de esta fase: BL (recuperación del prior, tilt positivo/
negativo, He-Litterman, separación BL/Kelly), Kelly (escalado, topes,
edge no positivo), comisiones (mínimo $1, tope 1%, ambas variantes del
filtro) y sizing (acciones enteras, no invertibles, derivación del nº de
posiciones, capital insuficiente → todo cash).
