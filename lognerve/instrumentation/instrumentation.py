import importlib
import logging
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


class Integration(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LANGCHAIN = "langchain"
    GOOGLE_GENAI = "google_genai"
    CREWAI = "crewai"
    OPENAI_AGENTS = "openai_agents"
    CLAUDE_AGENT_SDK = "claude_agent_sdk"
    LLAMA_INDEX = "llama_index"
    AUTOGEN = "autogen"
    AGNO = "agno"


_REGISTRY: Dict[Integration, Tuple[str, str]] = {
    Integration.OPENAI: ("openinference.instrumentation.openai", "OpenAIInstrumentor"),
    Integration.ANTHROPIC: ("openinference.instrumentation.anthropic", "AnthropicInstrumentor"),
    Integration.LANGCHAIN: ("openinference.instrumentation.langchain", "LangChainInstrumentor"),
    Integration.GOOGLE_GENAI: ("openinference.instrumentation.google_genai", "GoogleGenAIInstrumentor"),
    Integration.CREWAI: ("openinference.instrumentation.crewai", "CrewAIInstrumentor"),
    Integration.OPENAI_AGENTS: ("openinference.instrumentation.openai_agents", "OpenAIAgentsInstrumentor"),
    Integration.CLAUDE_AGENT_SDK: ("openinference.instrumentation.claude_agent_sdk", "ClaudeAgentSDKInstrumentor"),
    Integration.LLAMA_INDEX: ("openinference.instrumentation.llama_index", "LlamaIndexInstrumentor"),
    Integration.AUTOGEN: ("openinference.instrumentation.autogen", "AutogenInstrumentor"),
    Integration.AGNO: ("openinference.instrumentation.agno", "AgnoInstrumentor"),
}


def parse_integrations(values: Optional[Iterable[Any]]) -> List[Integration]:
    if values is None:
        return []
    integrations = []
    for value in values:
        try:
            integrations.append(value if isinstance(value, Integration) else Integration(str(value).strip()))
        except ValueError:
            logger.warning("lognerve: unknown integration %r; skipping", value)
    return integrations


def initialize_integrations(tracer_provider: Any, integrations: Iterable[Any]) -> List[Integration]:
    instrumented = []
    for integration in parse_integrations(integrations):
        module_name, class_name = _REGISTRY[integration]
        try:
            module = importlib.import_module(module_name)
            instrumentor = getattr(module, class_name)()
            if integration is Integration.AUTOGEN:
                instrumentor.instrument()
            else:
                instrumentor.instrument(tracer_provider=tracer_provider)
            instrumented.append(integration)
        except ModuleNotFoundError:
            logger.debug("lognerve: optional integration %s is not installed", integration.value)
        except Exception:
            logger.debug("lognerve: failed to instrument %s", integration.value, exc_info=True)
    return instrumented
