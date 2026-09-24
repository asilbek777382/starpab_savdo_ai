import logging

from app.ai.llm.base import LLMClient, LLMResponse, LLMUnavailable

log = logging.getLogger(__name__)


class FallbackLLM:
    """Asosiy provayder/model ishlamay qolsa, avtomatik zaxirasiga o'tadi."""

    def __init__(self, primary: LLMClient, secondary: LLMClient | None) -> None:
        self.primary, self.secondary = primary, secondary

    async def chat(self, **kwargs) -> LLMResponse:
        try:
            return await self.primary.chat(**kwargs)
        except LLMUnavailable:
            if self.secondary is None:
                raise
            log.warning("Asosiy LLM ishlamadi, zaxira modelga o'tildi")
            # Zaxira model o'z max_tokens qiymatidan foydalanadi (masalan, thinking uchun ko'proq)
            kwargs.pop("max_tokens", None)
            return await self.secondary.chat(**kwargs)
