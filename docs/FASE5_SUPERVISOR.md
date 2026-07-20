# Fase 5 — Supervisor IA (Capa 2.3)

El LLM actúa como **Comité de Inversión Final**: confirma o veta las
operaciones que los motores ya han sugerido, nunca propone nuevas. No es
backtesteable (Enmienda 7): su validación real es el paper trading, con el
mismo tratamiento que los motores live-only (spec 0.1).

## Diseño (`quantbot/supervisor/`)

- **Prompt versionado** (`prompts/v1.md`): guardado en el repo (spec 2.3).
  Cambiarlo crea una versión nueva; cada decisión persiste la versión y el
  texto completo usados, así que un cambio de prompt queda trazado.
- **Cliente LLM inyectable** (`llm_client.py`): `LLMClient` es un Protocol;
  `AnthropicClient` es la implementación real. La inyección permite testear
  el supervisor sin red (los tests pasan un cliente falso).
- **Structured outputs**: la llamada usa `output_config.format` con un
  esquema JSON estricto (`decision` ∈ {confirmed, vetoed} + `justification`)
  — garantiza una respuesta parseable sin recurrir a prefill (no soportado
  en Opus 4.8). Thinking adaptativo activado.
- **Supervisor** (`supervisor.py`): construye el mensaje con el score final,
  los scores por motor con su justificación y las noticias recientes; llama
  al LLM; parsea; y produce un `SupervisorVerdict` persistible.

## Reglas de reproducibilidad (spec 2.3) — implementadas y testeadas

1. **El veto exige justificación textual**: se valida en el parser Y por el
   constraint `veto_requires_justification` de la tabla (Fase 1). Un veto
   con justificación vacía lanza excepción.
2. **Persistencia inmutable**: modelo, versión de prompt, prompt completo y
   respuesta completa se guardan en `supervisor_decisions`, tabla
   append-only (trigger de Fase 1). Test verifica que un UPDATE falla.
3. **Autoridad confirm/veto únicamente**: el supervisor no tiene ninguna
   vía para proponer un activo que los motores no sugirieron — solo recibe
   candidatos y responde sí/no.

## Modelo y credenciales

- Modelo por defecto `claude-opus-4-8` (configurable con
  `QUANTBOT_SUPERVISOR_MODEL`), persistido en cada decisión.
- La API key se resuelve del entorno (`ANTHROPIC_API_KEY`) o de un perfil
  `ant auth login`; **nunca se fija en el repo**.

## Validación

- **Tests: 9, con cliente LLM falso** — flujo confirm, flujo veto,
  rechazo de veto sin justificación, rechazo de decisión inválida, rechazo
  de respuesta no-JSON, construcción del mensaje, y persistencia inmutable.
- **Smoke en vivo** (`scripts/supervisor_smoke.py`): requiere
  `ANTHROPIC_API_KEY`. Presenta dos candidatos (uno benigno, uno con una
  noticia de riesgo binario tipo decisión FDA) para verificar la
  integración de punta a punta. No se ejecutó en el entorno de desarrollo
  por no haber credencial; su función es de humo, no de validación (que es
  el paper trading).
