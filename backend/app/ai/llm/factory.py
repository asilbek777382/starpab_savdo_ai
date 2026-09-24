from app.ai.llm.anthropic_client import AnthropicLLM
from app.ai.llm.base import LLMClient
from app.ai.llm.fallback import FallbackLLM
from app.config import get_settings


def build_llm() -> LLMClient:
    s = get_settings()
    primary = AnthropicLLM(s.anthropic_api_key, s.llm_model, max_tokens=s.llm_max_tokens)
    secondary = None
    if s.llm_fallback_model and s.llm_fallback_model != s.llm_model:
        secondary = AnthropicLLM(s.anthropic_api_key, s.llm_fallback_model, max_tokens=8192)
    return FallbackLLM(primary, secondary)
