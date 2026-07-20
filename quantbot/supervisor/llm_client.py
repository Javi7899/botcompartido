"""LLM client abstraction for the supervisor.

The client is an injectable Protocol so the supervisor is testable without
network access (tests pass a fake). The real implementation uses the
Anthropic SDK with structured outputs (output_config.format) to guarantee
a parseable decision — no assistant prefill (unsupported on Opus 4.8).
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

DEFAULT_MODEL = "claude-opus-4-8"
MAX_TOKENS = 2000


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    text: str  # el JSON crudo devuelto por el modelo
    request_id: str | None = None


class LLMClient(Protocol):
    """Minimal surface the supervisor needs. `model` names the exact model
    version used, persisted with every decision for reproducibility."""

    model: str

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse:
        """Return the model's JSON response constrained to ``schema``."""
        ...


class AnthropicClient:
    """Real client (Anthropic SDK). Credentials resolve from the
    environment (ANTHROPIC_API_KEY or an `ant auth login` profile); nothing
    is hardcoded."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def complete(self, system: str, user: str, schema: dict) -> LLMResponse:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Con output_config.format el primer bloque de texto es JSON válido;
        # los bloques de thinking (si los hay) se ignoran.
        text = next(
            (b.text for b in response.content if b.type == "text"), None
        )
        if text is None:
            raise RuntimeError(
                f"respuesta del LLM sin bloque de texto "
                f"(stop_reason={response.stop_reason})"
            )
        return LLMResponse(
            model=response.model,
            text=text,
            request_id=response._request_id,
        )
