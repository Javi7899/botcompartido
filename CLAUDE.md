# CLAUDE.md — Reglas del proyecto

## Fuente de verdad

`docs/ARQUITECTURA.md` (v1.1) define la arquitectura completa, las fases y las enmiendas acordadas. Ante cualquier duda de diseño, ese documento manda. Si algo cambia de diseño, se edita primero allí (empezando por la tabla 0.0 si afecta a los motores) y luego se propaga al código.

## Reglas de desarrollo estrictas

1. **Paso a paso por fases:** solo se implementa lo que corresponde a la fase actual (ver Plan de Fases en el spec). Nunca escribir el sistema de golpe ni adelantar trabajo de fases futuras.
2. **Gate de fase:** no se avanza de fase sin (a) tests unitarios exhaustivos con `pytest`, (b) backtest walk-forward validado out-of-sample cuando aplique, y (c) aprobación explícita del usuario.
3. **Anti-overfitting:** cualquier motor o parámetro sin mejora estadísticamente significativa out-of-sample se simplifica o descarta; no se ajusta hasta que "funcione" en la muestra de desarrollo.
4. **Tipado estricto:** `pydantic` (o `dataclasses`) en todo el código.
5. **Fallas ruidosas:** excepciones claras si un API falla. Prohibido `try/except: pass`.
6. **Sin horas hardcodeadas:** toda lógica horaria usa `zoneinfo` con `America/New_York` y calendario de mercado dinámico (ver sección 1.1 del spec).
7. **Trazabilidad:** todo lo que el pipeline calcula se persiste en SQLite, incluso los días en que no se envían órdenes.

## Flujo de trabajo con git

- Remoto: `https://github.com/Javi7899/botcompartido.git` (`origin`), rama principal `main`.
- **Todo el trabajo se sincroniza 1:1 con GitHub:** cada commit se pushea a `origin` para que Javi tenga siempre el estado actual. Confirmar con el usuario antes de cada push.
- Commits pequeños y descriptivos, en español, uno por unidad lógica de trabajo.

## Idioma

Documentación, commits y comunicación con el usuario en español. Nombres de código (variables, funciones, módulos) en inglés.
