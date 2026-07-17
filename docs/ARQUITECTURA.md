# Construcción Paso a Paso de Bot Cuantitativo

> **Versión 1.1** — Documento original + Enmiendas acordadas (ver sección final).
> Este documento es la **fuente de verdad** de la arquitectura del proyecto.

Rol de referencia: Ingeniero de Software Cuantitativo Senior experto en Python, arquitecturas limpias orientadas a eventos, estadística bayesiana, optimización de carteras y automatización con la API de Interactive Brokers (`ib_insync` / `ib_async`).

Vamos a construir un bot de trading cuantitativo desde cero para una cuenta de 5.000€ (broker: Interactive Brokers Pro, plan de comisiones Fija). Es un sistema altamente complejo, por lo que **NUNCA se debe intentar escribir todo el sistema de golpe**. Se trabaja de forma estrictamente modular y en Fases. No se pasa a la siguiente Fase ni se programa el siguiente motor hasta que el actual tenga pruebas unitarias exhaustivas (`pytest`), un backtest riguroso *walk-forward* validado y la aprobación explícita del usuario.

## 0. PRINCIPIOS DE RIESGO Y REALISMO (léelos antes de todo)

- **Riesgo de overfitting:** este sistema tiene muchos grados de libertad (7 motores, ponderación bayesiana jerárquica, optimizador, supervisor IA). Cada fase debe incluir explícitamente una validación *out-of-sample* real (periodo nunca visto durante el desarrollo de esa fase) antes de darla por buena. Si un motor o parámetro no aporta mejora estadísticamente significativa fuera de muestra, se descarta o se simplifica, no se ajusta hasta que "funcione".
- **Capital limitado:** 5.000€ concentrados en un máximo de 10-20 posiciones (ver Enmienda 1) implica posiciones de ~300-400€ cada una. El sistema debe evitar la sobre-rotación: cualquier rebalanceo debe pasar el Filtro de Comisiones (sección 3) antes de generar una orden real.
- **Punto de partida conservador:** en cada fase, preferimos un modelo simple que funcione y esté bien testeado sobre uno complejo sin validar. La complejidad (GEX, Black-Litterman+Kelly) se añade *después* de que el esqueleto base (motores más simples + ejecución) esté probado en real o en paper trading durante un tiempo razonable.

### 0.0 Tabla única de motores (fuente de verdad)

Para evitar que la Capa 2.1, la Fase 3 y la sección 0.1 se desalineen entre sí sobre cuántos motores hay, en qué orden se construyen y qué régimen de datos/backtest les aplica, esta tabla es la referencia única. Cualquier cambio de orden o de régimen se edita aquí primero y se propaga al resto del documento.

| # | Motor | Datos usados | Régimen temporal | Backtest walk-forward riguroso |
|---|---|---|---|---|
| 1 | Técnico | Precio/volumen (OHLCV) | T-1 (cierre oficial de sesión anterior) | Sí |
| 2 | Fundamental | Ratios y métricas financieras | T-1, con mitigación explícita de look-ahead bias (ver 1.1) | Reducido — ver 0.1 |
| 3 | Series Temporales | Serie histórica de precios (ARIMA/Prophet) | T-1 (cierre oficial) | Sí |
| 4 | Machine Learning (XGBoost) | Features derivadas de datos T-1 | T-1 | Sí |
| 5 | Insider Trading | Form 4 SEC (EDGAR) | T-1, con delay de reporte de hasta 2 días hábiles | Sí |
| 6 | GEX (Gamma Exposure) | Cadena de opciones (OI, IV) vía yfinance | T-1 (OI de cierre del día anterior) | Sí |
| 7 | Macro y Noticias (NLP) | RSS/APIs de noticias, contexto macro | Tiempo real hasta el momento exacto de ejecución (excepción explícita, ver 1) | Reducido — ver 0.1 |

El orden de construcción en Fase 3 sigue esta misma tabla de arriba a abajo.

> **Nota (Enmienda 5):** el motor de Reinforcement Learning (PPO + TimeGAN) que figuraba como motor 8 en la versión 1.0 queda **eliminado del alcance del proyecto**. Se documenta como posible extensión futura, condicionada a que el resto del sistema lleve tiempo validado en real y a una decisión explícita nueva.

## 0.1 Motores sin backtest histórico riguroso viable (Noticias y Fundamentales point-in-time)

Conseguir datos históricos de noticias con timestamp exacto, y datos fundamentales verdaderamente point-in-time, es costoso e inviable con fuentes gratuitas. Se acepta no exigir a estos dos motores (2.1.2 Fundamental y 2.1.7 Noticias) el mismo nivel de backtest walk-forward riguroso que al resto — su validación real se hará con el histórico acumulado durante la Fase 8 (Paper Trading). Esto no significa que se lancen sin ninguna estructura de validación; se aplican estas reglas obligatorias como compensación:

1. **Peso inicial conservador:** ambos motores arrancan con un peso bajo en el ponderador bayesiano (Capa 2.2), inferior al de los motores sí validados en backtest histórico, hasta que el paper trading acumule suficientes observaciones para ajustar su peso con confianza estadística razonable.
2. **El paper trading se trata como su backtest:** desde el primer día de Fase 8, cada predicción de estos dos motores (score, justificación, fuente de datos usada) se persiste en SQLite exactamente igual que el resto, junto con el resultado real posterior del activo, para poder evaluar su capacidad predictiva de forma acumulativa según pasan las semanas/meses de paper trading.
3. **Vigilancia específica del riesgo de look-ahead bias en Fundamental:** dado que este es el motor con mayor riesgo conocido de look-ahead bias oculto (datos de yfinance no necesariamente point-in-time, ver 1.1), su comportamiento en paper trading debe revisarse con especial atención antes de aumentar su peso o de pasar a Fase 9 (capital real, ver Plan de Fases en la sección 5).

> **Nota (Enmienda 7):** el Supervisor IA (Capa 2.3) recibe el mismo tratamiento que estos dos motores: no es backtesteable históricamente (no existen noticias point-in-time gratuitas y el modelo LLM cambia entre versiones), así que su validación es el paper trading, con prompt versionado y persistencia inmutable de inputs/outputs como ya exige la Capa 2.3.

## 1. MERCADO, CADENCIA Y DATOS

- **Mercado y Activos:** Universo selecto de 30-40 "Blue Chips" de EEUU (S&P 500), elegidos por alta liquidez y baja volatilidad idiosincrática. **El universo es el conjunto de candidatos, no la cartera** (ver Enmienda 1): la cartera se concentra en las mejores señales, con un máximo de 10-20 posiciones simultáneas.
- **Divisa (Enmienda 4):** conversión única de los 5.000€ a USD el primer día de operativa. Todo el sistema (posiciones, cash, contabilidad interna, filtro de comisiones) opera exclusivamente en USD. La exposición EURUSD resultante es una decisión deliberada y documentada; no se cubre.
- **Cadencia:** El bot corre **una vez al día**, en una ventana horaria con margen de seguridad respecto al cutoff real de mercado (ver 1.1). No se ejecuta "a cualquier hora".
- **Datos T-1 → Señal → Ejecución T (MOC), con una excepción explícita (noticias):** el bot descarga precios de cierre y datos relevantes de la sesión anterior (T-1), genera señales, y envía órdenes MOC (Market On Close) para que se ejecuten al cierre de la sesión en curso (T). **Excepción deliberada:** el motor de Macro y Noticias (2.1.7) no se limita a T-1; usa la información más reciente disponible en el momento exacto de ejecución del bot (ver nota en 1.1), porque en este caso más recencia es estrictamente mejor y no hay razón para descartar noticias ya publicadas ese mismo día. El resto de motores basados estrictamente en la dinámica estadística de una serie temporal de precios con frecuencia de muestreo constante (Técnico y Series Temporales en particular) usan **exclusivamente el precio de cierre oficial de sesiones anteriores**, nunca un precio intradía a la hora de ejecución, para no romper esa consistencia de muestreo de la que dependen sus supuestos estadísticos. El motor Fundamental también opera en T-1, pero por una razón distinta: no es una cuestión de frecuencia de muestreo (los datos fundamentales no se publican con cadencia diaria), sino de evitar look-ahead bias usando el dato tal como se conocía en cada fecha histórica — ver la advertencia explícita sobre yfinance en 1.1.

### 1.1 Ventana de ejecución

Las órdenes MOC en NYSE/Nasdaq tienen cutoffs estrictos en hora de mercado (ET), **no un horario fijo en hora española**, porque España y EEUU no cambian de horario de verano/invierno en las mismas fechas (hay 1-2 semanas de desfase al año).

- Cutoff real de mercado: envío de nuevas órdenes MOC antes de las **15:50 ET**; entre 15:50-15:58 ET solo se permiten reducciones de una orden ya enviada; después de 15:58 ET no se puede modificar nada.
- **Hora de ejecución variable día a día (no fija), con objetivo de ejecutar lo más tarde posible dentro de margen seguro:** el usuario ejecutará el bot manualmente cada día, intentando lanzarlo lo más tarde posible dentro de la sesión (para maximizar la recencia de datos del motor de Noticias, ver más abajo). Algunos días, por disponibilidad del usuario, podrá ejecutarse más temprano (ej. 17:00 España). El sistema **no debe tener ninguna hora fija hardcodeada**; debe tratar la hora de ejecución como variable en cada lanzamiento, detectarla dinámicamente, y aplicar siempre las mismas validaciones de margen de seguridad y calendario de mercado (ver regla obligatoria más abajo) sea cual sea la hora concreta ese día. Además, el sistema debe **registrar en SQLite la hora exacta de ejecución de cada día** (junto con el resto de trazabilidad de la sección 4), para poder analizar en el futuro si la variabilidad de horario tiene algún efecto observable en el resultado (especialmente relevante para el motor de Noticias).
- **Nota a futuro:** si en una fase posterior se añadiera alguna señal basada en datos del día en curso (ej. momentum intradía, GEX recalculado con precio actual), entonces sí aparecería una diferencia real de información entre ejecutar temprano o tarde para esa señal concreta, y habría que revisar la hora de ejecución en ese momento. Con el diseño actual (Técnico/Series Temporales/Fundamental estrictamente T-1), esto no aplica a esos motores.
- **Caso ya presente hoy — motor de Noticias:** el motor de Macro y Noticias (2.1.7) sí usa información hasta el momento exacto de ejecución (no solo T-1, ver 1). Esto significa que, para ese motor concreto, ejecutar más tarde en la sesión (ej. 20:50 España) sí captura más noticias reales del día que ejecutar más temprano (ej. 17:00 España). Esta asimetría entre motores (unos estrictamente T-1, el de noticias hasta "ahora mismo") es una decisión de diseño deliberada, pero tiene una implicación crítica para el backtest: la validación histórica del motor de Noticias debe simular fielmente qué noticias existían publicadas en el instante exacto de ejecución de cada día histórico, nunca las noticias de todo ese día completo, o se introduce look-ahead bias. Si la hora de ejecución final se fija en un valor concreto (ej. 17:00), el backtest del motor de Noticias debe usar ese mismo corte horario de forma consistente.
- **Regla obligatoria (independiente de la hora elegida):** el código NUNCA debe asumir un offset horario fijo España↔ET, ni asumir que el día es siempre una sesión normal. Antes de enviar cualquier orden, el bot debe:
  1. Calcular la hora ET real en el momento de ejecución (librería de zonas horarias, ej. `zoneinfo`/`pytz` con `America/New_York`).
  2. Consultar el calendario de mercado (festivos USA y días de cierre anticipado, ej. el día después de Acción de Gracias) de forma dinámica, no hardcodeada, para confirmar que hay sesión ese día y a qué hora es el cierre real.
  3. Verificar que quedan al menos 15-20 minutos de margen antes del cutoff real antes de empezar a enviar órdenes.
  - **Si no queda margen suficiente, o el mercado está cerrado/tiene horario especial ese día, el bot aborta únicamente el envío de órdenes al broker, de forma ruidosa (log + email).** El resto del pipeline (descarga de datos, cálculo de los 7 motores, ponderación bayesiana, supervisor IA, cálculo de Black-Litterman/Kelly) se ejecuta y se persiste en SQLite igualmente ese día, para no perder trazabilidad ni continuidad de las series usadas en Fase 4 (bayesiano) y Fase 8 (paper trading). Lo único que no ocurre es el envío real de órdenes MOC.

- **Fuentes de datos gratuitas:** `yfinance` para OHLCV, FRED para macro, RSS/APIs libres para noticias. **Advertencia explícita a validar en Fase 2:** los datos fundamentales de yfinance no son necesariamente *point-in-time* (pueden reflejar el valor conocido hoy, no el valor tal como se conocía en la fecha histórica). Cualquier motor que use datos fundamentales en el backtest debe documentar y mitigar este riesgo de look-ahead bias explícitamente, o descartar ese dato si no se puede verificar.

## 2. EL CEREBRO (Motores de Señales y Meta-Modelo)

Arquitectura de decisión en tres capas.

### Capa 2.1 - Los 7 Motores Base

Cada motor se construye y prueba de forma aislada (Fase 3), en el orden y con el régimen de datos definidos en la tabla de la sección 0.0. Deben devolver un *score* estandarizado (-1.0 a 1.0), con su metodología y limitaciones documentadas.

1. **Técnico:** Indicadores clásicos de precio/volumen.
2. **Fundamental:** Métricas financieras y ratios (con mitigación de look-ahead bias, ver 1.1).
3. **Series Temporales:** Predicciones estadísticas (ARIMA/Prophet).
4. **Machine Learning (XGBoost):** Modelo predictivo de features.
5. **Insider Trading:** Analiza transacciones de insiders (ejecutivos, directores, accionistas significativos) reportadas en el **Form 4** de la SEC vía EDGAR (fuente pública y gratuita).
   - Filtrar explícitamente: compras en mercado abierto (señal relevante) vs. ejercicio de stock options o ventas rutinarias programadas (Rule 10b5-1, no son señal real).
   - Tener en cuenta el delay de reporte (hasta 2 días hábiles) al construir el score y evitar look-ahead bias.
   - Ponderar el score por seniority del insider (compras de CEO/CFO pesan más que de directores menores) y por tamaño relativo de la transacción respecto a su patrimonio conocido en la empresa, si es calculable.
6. **GEX (Gamma Exposure):** Mide la exposición gamma de los market makers de opciones sobre el activo, para detectar zonas de "pinning" (baja volatilidad esperada) o posible aceleración de movimiento (gamma negativa). Decisiones de diseño:
   - Se calcula únicamente sobre un **subconjunto reducido de tickers** (5-10 blue chips con mayor liquidez de opciones, ej. las tecnológicas grandes), no sobre los 30-40, dado el límite de fuentes de datos gratuitas.
   - Cálculo propio (no API de terceros): descarga de cadena de opciones vía `yfinance` (OI, IV por strike y vencimiento) y cálculo de gamma vía Black-Scholes.
   - Fórmula base: gamma exposure por strike = OI × gamma (Black-Scholes) × precio del subyacente × multiplicador de contrato, con el signo asignado según la convención estándar de mercado (dealers cortos de calls que compran los clientes, largos de puts que venden los clientes).
   - Los datos de open interest son de cierre del día anterior (coherente con la arquitectura T-1 general), y el cálculo es una **estimación basada en convenciones**, no una medición exacta. **Limitación adicional a documentar:** al usar OI de T-1 sobre el precio del subyacente en T, un movimiento de precio significativo entre el cierre anterior y la sesión en curso puede desplazar el spot fuera de la zona de strikes donde el OI de T-1 sigue siendo representativo, especialmente en blue chips muy líquidas donde el gap intersesión puede ser relevante — el motor debe dejar constancia de esto como limitación conocida, no solo de la naturaleza convencional del cálculo de gamma.
   - Para tickers fuera del subconjunto de opciones líquidas, el motor devuelve un score neutro (0) o se excluye de la ponderación bayesiana para ese activo.
   - **Validación obligatoria antes de dar el motor por bueno (Fase 3), en cuatro niveles:**
     1. *Validación de la fuente de datos:* antes de construir el motor, comparar el OI total y la IV que devuelve `yfinance` para 2-3 tickers en un día concreto contra los datos públicos visibles en la web de CBOE o la del propio broker, para confirmar que no vienen incompletos o desfasados. Si `yfinance` no es fiable para algún ticker, excluirlo del subconjunto GEX.
     2. *Test unitario con caso manual:* construir un caso de prueba con 2-3 strikes, OI y gamma conocidos, calculado a mano o en hoja de cálculo, y verificar que el código reproduce exactamente ese resultado. Esto valida la lógica del código, no la calidad de los datos de mercado.
     3. *Validación cruzada contra una fuente de referencia externa:* para 3-5 tickers muy líquidos (ej. SPY, AAPL, NVDA), comparar el Call Wall, Put Wall, Gamma Flip y el signo de la GEX neta del mismo día contra los que publica alguna herramienta gratuita ya existente de gamma exposure. No hace falta que coincida el número exacto en dólares (los supuestos varían entre proveedores), pero los niveles de strike clave y el signo del régimen deben ser razonablemente consistentes.
     4. *Test de consistencia temporal:* comprobar que el gamma flip y los walls no saltan de forma errática día a día sin un motivo claro (movimiento de precio grande, vencimiento de opciones); saltos incoherentes sin ese contexto indican un bug en el pipeline (ej. mezclar expiraciones, IV mal calculada).
7. **Macro y Noticias (NLP):** Análisis de sentimiento de noticias del ticker y contexto macroeconómico.

### Capa 2.2 - El Ponderador Bayesiano Jerárquico (global → por activo, con shrinkage)

*(Redefinida por la Enmienda 2 — sustituye al ponderador por-activo puro de la v1.0.)*

El objetivo sigue siendo el original: que si en AAPL el análisis técnico predice mejor que el fundamental, el técnico pese más *en AAPL*, y que si en NVDA ocurre lo contrario, el fundamental pese más *en NVDA*. Pero un ponderador por-activo puro (7 motores × 30-40 activos ≈ 250+ parámetros libres estimados con datos diarios ruidosos) es ruido garantizado. La solución es un **modelo jerárquico con shrinkage**:

- Cada motor tiene un **peso global** (prior), estimado con la evidencia agregada de todos los activos.
- El peso de cada motor **en cada activo** parte de ese peso global y solo se desvía de él en proporción a la evidencia acumulada específica de ese activo. Con poca evidencia, el peso por activo ≈ peso global; con evidencia abundante y consistente, se aleja de él cuanto haga falta.
- La fuente de evidencia depende del motor: los motores backtesteables (Técnico, Series Temporales, XGBoost, Insider, GEX) aportan evidencia desde el backtest walk-forward de Fase 3/4; Fundamental y Noticias solo acumulan evidencia desde el paper trading (coherente con 0.1), por lo que sus pesos por activo permanecerán cerca del global (bajo) durante más tiempo.
- Los pesos se actualizan según los resultados de un backtest walk-forward riguroso (sin look-ahead bias) y, desde Fase 8, con los resultados del paper trading.
- El sistema calcula además una matriz de correlación entre activos para evitar sobreexposición a un mismo factor de riesgo.
- Los motores GEX e Insider, al no aplicar a todos los activos, se excluyen del cálculo bayesiano para los activos donde no hay dato disponible (no se imputan con un valor neutro que distorsione el peso).

### Capa 2.3 - El Supervisor IA (Segunda Fase de Decisión)

El LLM actúa como Comité de Inversión Final, no como motor de señales adicional. Recibe:
- El score final ponderado (post-bayesiano) del activo.
- Los scores individuales de los 7 motores para ese activo, con breve justificación de cada uno.
- Noticias y contexto textual reciente relevante del activo (últimas 24-48h), obtenido de una fuente RSS/API gratuita definida en Fase 2.

Tiene autoridad para **confirmar o vetar** el trade sugerido, nunca para proponer un trade que los motores no hayan sugerido. Reglas obligatorias para mantener reproducibilidad:
- El prompt exacto que recibe el LLM debe **versionarse** (guardarse en el repositorio con número de versión). Cualquier cambio de prompt invalida los backtests anteriores del supervisor y debe quedar registrado en el changelog.
- El modelo, la versión del modelo, el prompt completo enviado, y la respuesta completa recibida se persisten en SQLite de forma inmutable para cada decisión (ver sección 4).
- El veto del LLM debe venir siempre acompañado de una justificación textual persistida, nunca solo un booleano.
- **(Enmienda 7)** El supervisor no es backtesteable históricamente: su validación es el paper trading de Fase 8, igual que los motores de la sección 0.1.

## 3. CARTERA, OPTIMIZACIÓN Y RIESGO (Capital: 5.000€ → USD)

- **Concentración de cartera (Enmienda 1):** el universo de 30-40 candidatos NO implica 30-40 posiciones. La cartera mantiene un **máximo de 10-20 posiciones simultáneas** (parametrizable), con un **tamaño mínimo de posición ~300€ (~$320-350)**. Esto hace viable operar con acciones enteras vía MOC.
  - **Restricción de acciones enteras:** las órdenes MOC de IBKR no admiten fracciones de acción. El optimizador debe redondear los pesos objetivo a números enteros de acciones y evaluar el impacto del redondeo.
  - **Tickers no invertibles:** los tickers cuyo precio por acción supere el tamaño de posición objetivo (ej. acciones de $800-1000) quedan documentados como no invertibles con este capital y se excluyen de la cartera (pueden permanecer en el universo a efectos de señal/correlación).
- **Optimizador Black-Litterman:** convierte los scores de los motores (post-ponderación bayesiana y post-supervisor IA) en "views" del modelo Black-Litterman, combinadas con un prior de equilibrio de mercado (derivado de capitalización bursátil de las blue chips del universo), para generar los pesos objetivo de cartera. Esto sustituye una asignación puramente equal-weight o ad-hoc por una asignación matemáticamente coherente entre señal y equilibrio de mercado.
- **Dimensionamiento con Kelly Fraccionario:** una vez que Black-Litterman determina los pesos relativos entre activos, se usa el criterio de Kelly en versión fraccionaria (ej. 25-50% del Kelly completo, parametrizable) para determinar la exposición total de la cartera dado el edge y varianza estimados, evitando el sobre-apalancamiento que produciría un Kelly completo con estimaciones imperfectas de probabilidad.
- **Filtro Estricto de Comisiones (regla de rebalanceo):** el bot se ejecuta todos los días, pero solo genera una orden real si se cumplen conjuntamente:
  1. La desviación del peso actual respecto al peso objetivo supera un umbral mínimo (parametrizable, ej. ±0.5-1 punto porcentual).
  2. El beneficio matemático esperado del ajuste supera en al menos 3x la comisión estimada de IBKR para esa operación.
  - **Nivel de aplicación del filtro (a decidir y fijar explícitamente en Fase 6, no dejar implícito):** el filtro puede evaluarse (a) por posición individual, bloqueando solo los ajustes que no superen el umbral por sí solos, o (b) sobre el rebalanceo agregado de la cartera completa, permitiendo que ajustes individualmente pequeños se ejecuten si el conjunto del rebalanceo del día sí supera el umbral agregado. El criterio elegido cambia sustancialmente qué rebalanceos se ejecutan. Ambas variantes (y sus parámetros) deben implementarse de forma configurable y compararse en el backtest de Fase 6 antes de fijar una por defecto.
  - **Expectativa documentada (Enmienda 6):** con el mínimo de $1/orden de IBKR Fija, los ajustes pequeños (decenas de €) tienen una comisión relativa del 1-3% y el filtro 3x los bloqueará sistemáticamente. Esto es **comportamiento esperado por diseño**, no un bug: el sistema tenderá a baja rotación y a ejecutar solo rebalanceos con edge esperado sustancial.

## 4. INFRAESTRUCTURA, TRAZABILIDAD Y ROBUSTEZ

1. **Tipado estricto:** `pydantic` o `dataclasses` en todo el código.
2. **Fallas ruidosas:** excepciones claras si un API falla. Nada de `try/except: pass`.
3. **Trazabilidad SQLite inmutable:** persistir predicciones de cada motor por activo, peso bayesiano del día (global y por activo), inputs/outputs completos del LLM supervisor, pesos de Black-Litterman, tamaño de Kelly aplicado, y fills reales del broker reconciliados al día siguiente. Esta persistencia ocurre siempre que el pipeline corre, incluso en los días en que el envío de órdenes se aborta por falta de margen horario (ver 1.1).
4. **Reconciliación y tolerancia a fallos de conexión:** si la conexión con IBKR se interrumpe a mitad del envío de órdenes de rebalanceo, el sistema debe:
   - Registrar el estado de cada orden (enviada/confirmada/fallida) antes de cualquier reintento.
   - Nunca reenviar una orden sin verificar primero, contra el propio IBKR, si ya se ejecutó (para evitar duplicados).
5. **Notificaciones:** email para reportes y alertas críticas, más un log local persistente como respaldo (para no depender de un único canal si el envío de email falla).

## 5. PLAN DE FASES

*NO programar nada hasta la aprobación explícita de la fase correspondiente.*

- **FASE 1:** Infraestructura y Base de Datos (config, Loguru, SQLAlchemy).
- **FASE 2:** Ingesta de Datos y Limpieza (yfinance, FRED, gestión de splits/dividendos, validación explícita de point-in-time data para evitar look-ahead bias, validación de la calidad de datos de opciones de yfinance para el subconjunto GEX, fuente de datos de noticias/RSS).
- **FASE 3:** Desarrollo Motor a Motor — construcción, test unitario y backtest walk-forward aislado para cada uno de los 7 motores, uno por uno, en el orden definido en la tabla de la sección 0.0: Técnico → Fundamental → Series Temporales → ML (XGBoost) → Insider Trading → GEX → Macro/Noticias (NLP).
- **FASE 4:** Meta-Modelo y Correlaciones — ponderación bayesiana jerárquica (global → por activo con shrinkage, ver Capa 2.2) basada en resultados de Fase 3, matriz de correlación entre activos.
- **FASE 5:** Supervisor IA — integración del prompt LLM versionado, con acceso a scores y noticias, persistencia completa de inputs/outputs.
- **FASE 6:** Optimización de Cartera — Black-Litterman + Kelly fraccionario, restricción de acciones enteras y máximo de posiciones (Enmienda 1), y Filtro de Comisiones (umbral de desviación + regla de 3x comisión, con el nivel de aplicación —individual vs. agregado— decidido y testeado explícitamente, ver sección 3).
- **FASE 7:** Ejecución MOC — conexión `ib_insync`/`ib_async`, cálculo de ventana horaria real (ET dinámico), conversión inicial EUR→USD (Enmienda 4), reconciliación de órdenes, envío de emails y logging de respaldo.
- **FASE 8:** Paper Trading — validación en real con dinero simulado. **Antes de iniciar esta fase deben quedar pre-registrados por escrito los criterios de éxito (Enmienda 3):** benchmark (SPY buy-and-hold), duración mínima (6 meses), Sharpe mínimo y drawdown máximo tolerable. La evaluación de Fase 8 se hace contra esos criterios, no de forma subjetiva.
- **FASE 9:** Capital Real — activación con dinero real, condicionada a que los resultados acumulados de Fase 8 cumplan los criterios pre-registrados (en particular, revisión explícita del comportamiento de los motores Fundamental y Noticias antes de ampliar su peso, ver 0.1) y a la aprobación explícita del usuario.

## 6. REGLAS DE DESARROLLO ESTRICTAS

1. **Paso a paso:** solo se implementa lo que se pida en la fase actual.
2. **Sin backtest walk-forward validado y aprobación explícita del usuario, no se avanza de fase.**
3. Cualquier motor o parámetro que no muestre mejora estadísticamente significativa out-of-sample se simplifica o descarta, no se sigue ajustando hasta que "funcione" en la muestra de desarrollo.

---

## ENMIENDAS v1.1 (revisión inicial, 2026-07-17)

Decisiones acordadas tras la revisión del documento original. Ya están integradas en el texto de arriba; esta sección las resume con su justificación.

1. **Universo ≠ cartera; máximo 10-20 posiciones; acciones enteras.** El documento v1.0 implicaba 30-40 posiciones de ~125-165€, incompatible con dos realidades: (a) muchas blue chips cotizan por encima de ese importe por acción (no se puede comprar ni 1 acción), y (b) las órdenes MOC de IBKR no admiten fracciones. Decisión: el universo de 30-40 tickers es el conjunto de *candidatos*; la cartera se concentra en las mejores señales con un máximo de 10-20 posiciones (~300-400€ cada una), el optimizador redondea a acciones enteras, y los tickers con precio/acción superior al tamaño de posición se documentan como no invertibles.
2. **Ponderador bayesiano jerárquico con shrinkage.** Un ponderador por-activo puro (7×35 ≈ 250 parámetros con datos diarios ruidosos) es overfitting garantizado; uno global puro pierde la diferenciación por activo que se busca (técnico en AAPL vs. fundamental en NVDA). Decisión: modelo jerárquico — prior global por motor, desviación por activo proporcional a la evidencia acumulada. Los motores backtesteables aportan evidencia histórica; Fundamental y Noticias solo desde paper trading (coherente con 0.1).
3. **Criterios de éxito pre-registrados.** Sin criterios fijados *antes*, la evaluación del paper trading sería subjetiva. Decisión: benchmark SPY buy-and-hold, mínimo 6 meses de paper trading, umbrales concretos de Sharpe y drawdown máximo escritos y versionados antes de iniciar Fase 8. Además: el universo de backtest se congela y documenta a fecha de inicio para dejar constancia del survivorship bias (elegir las blue chips de hoy para backtests históricos ya es una forma de look-ahead).
4. **Divisa: conversión única EUR→USD el día 1.** Todo el sistema opera en USD. La exposición EURUSD es una decisión deliberada, documentada y no cubierta. Elimina complejidad de conversión en cada operación.
5. **Motor RL (PPO + TimeGAN) eliminado.** Coste de desarrollo y fragilidad altísimos, valor esperado ≈ 0 con este capital y estas fuentes de datos. Queda fuera del alcance; solo se revisitaría con el sistema completo validado en real y una decisión explícita nueva. El sistema queda en **7 motores**.
6. **Expectativa de comisiones documentada.** El mínimo de $1/orden hace que el filtro 3x bloquee ajustes pequeños por diseño; el sistema tenderá a baja rotación. Comportamiento esperado, no bug. Con 5.000€ este es un sistema de aprendizaje y validación de proceso, no de renta.
7. **Supervisor LLM no backtesteable.** Recibe el mismo tratamiento que la sección 0.1: su validación es el paper trading, con prompt versionado y persistencia inmutable (ya previstas en la Capa 2.3).
