import anthropic

from app.ai.llm.base import LLMError, LLMResponse, LLMUnavailable, Usage


class AnthropicLLM:
    """Claude Messages API. System prompt (do'kon ma'lumoti) keshlanadi — u har so'rovda bir xil."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 2048,
        timeout: float = 60.0,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.client = client or anthropic.AsyncAnthropic(api_key=api_key or None, timeout=timeout, max_retries=2)
        self.model = model
        self.max_tokens = max_tokens

    async def chat(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            resp = await self.client.messages.create(**kwargs)
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as exc:
            raise LLMUnavailable(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMUnavailable(str(exc)) from exc
            raise LLMError(str(exc)) from exc

        u = resp.usage
        usage = Usage(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        # Bloklar o'zgarishsiz qaytariladi (thinking bloklari ham keyingi so'rovga shu holida borishi kerak)
        content = [block.model_dump(mode="json", exclude_none=True) for block in resp.content]
        return LLMResponse(content=content, stop_reason=resp.stop_reason or "", usage=usage, model=resp.model)
