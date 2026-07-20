# Motor de Noticias (Fase 3.7) — diseño y validación en vivo

Motor 7 de la tabla 0.0. **Live-only** (spec 0.1): no existe histórico
gratuito de noticias con timestamp exacto, así que se valida en paper
trading. El archivo point-in-time (`news_items`, append-only) se acumula
desde la Fase 2 precisamente para hacer esa evaluación posible.

## Excepción temporal deliberada (spec 1)

Único motor que **no** se limita a T-1: usa las noticias publicadas hasta
el momento exacto de ejecución del bot, porque aquí más recencia es
estrictamente mejor. Esta asimetría con el resto de motores es una decisión
de diseño documentada; el supervisor LLM (Capa 2.3) es quien lee el texto
completo con contexto — este motor solo produce un score cuantitativo.

## Diseño (`quantbot/engines/news_nlp.py`, v1.0-lexicon-lm)

- Sentimiento por **léxico financiero** embebido, inspirado en las listas
  Loughran-McDonald (el estándar académico para texto financiero; los
  léxicos genéricos fallan — "liability" no es negativo en un balance).
- Score por titular: (positivas − negativas) / (positivas + negativas).
- Score del ticker: media de los titulares de las últimas 48 h, ponderada
  por recencia (semivida 24 h desde la publicación al momento de
  ejecución), pasada por tanh(2·media). Sin titulares con carga → 0.

## Validación en vivo (2026-07-20)

`scripts/score_news_universe.py`, sentimientos coherentes con los titulares
reales del momento:

| Ticker | Score | Titulares con señal |
|---|---|---|
| TSLA | +0.82 | 5 (sentimiento +0.58) |
| AAPL | +0.78 | 7 (sentimiento +0.53) |
| NVDA | +0.27 | 7 |
| MSFT | +0.20 | 9 |
| JPM | −0.42 | 5 |
| PFE | −0.96 | 2 (sentimiento −1.00) |

De cada 20 titulares descargados, ~5-9 llevan carga de sentimiento y el
resto son neutros — proporción razonable para titulares financieros.

## Limitaciones conocidas (candidatas a v2)

- Sin manejo de negaciones ("not strong") ni ironía.
- Sin contexto macro (los feeds FRED/macro ya almacenados podrían
  integrarse en una v2).
- Léxico de titular, no de cuerpo completo: rápido y robusto, pero pierde
  matices. El supervisor LLM compensa esto en la Capa 2.3.

Su capacidad predictiva se medirá acumulativamente en paper trading.
