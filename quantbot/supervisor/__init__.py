"""LLM supervisor (Capa 2.3): investment-committee veto layer.

Not backtestable (Enmienda 7): validated in paper trading. The prompt is
versioned in prompts/, and every decision persists model + version +
full prompt + full response immutably (spec 2.3).
"""

from quantbot.supervisor.llm_client import (
    AnthropicClient,
    LLMClient,
    LLMResponse,
)
from quantbot.supervisor.supervisor import (
    DECISION_SCHEMA,
    Supervisor,
    SupervisorVerdict,
    TradeCandidate,
    load_prompt,
)

__all__ = [
    "AnthropicClient",
    "DECISION_SCHEMA",
    "LLMClient",
    "LLMResponse",
    "Supervisor",
    "SupervisorVerdict",
    "TradeCandidate",
    "load_prompt",
]
