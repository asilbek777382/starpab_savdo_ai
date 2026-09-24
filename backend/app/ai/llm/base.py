"""Provayderdan mustaqil LLM interfeysi.

Ichki format sifatida Messages API ko'rinishidagi content bloklari (dict) ishlatiladi:
{"type": "text", "text": ...}, {"type": "tool_use", "id", "name", "input"},
{"type": "tool_result", "tool_use_id", "content"}. Boshqa provayder adapteri shu formatga o'giradi.
"""

from dataclasses import dataclass, field
from typing import Protocol


class LLMError(Exception):
    """Qayta urinishdan foyda yo'q xato (noto'g'ri so'rov va h.k.)."""


class LLMUnavailable(LLMError):
    """Provayder vaqtincha ishlamayapti: fallback yoki standart javob kerak."""


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __iadd__(self, other: "Usage") -> "Usage":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        return self

    @property
    def total_in(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass
class LLMResponse:
    content: list[dict]
    stop_reason: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""

    @property
    def text(self) -> str:
        return "\n".join(b["text"] for b in self.content if b.get("type") == "text" and b.get("text")).strip()

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [
            ToolCall(id=b["id"], name=b["name"], input=b.get("input") or {})
            for b in self.content
            if b.get("type") == "tool_use"
        ]


class LLMClient(Protocol):
    async def chat(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...
