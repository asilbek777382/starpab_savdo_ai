"""Testlar uchun soxta LLM va Telegram bot."""

import itertools
from collections.abc import Callable
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.methods import SendMediaGroup, SendMessage, SendPhoto
from aiogram.types import Chat, Message, PhotoSize

from app.ai.llm.base import LLMResponse, LLMUnavailable, Usage


def text_response(text: str) -> LLMResponse:
    return LLMResponse(content=[{"type": "text", "text": text}], stop_reason="end_turn", usage=Usage(100, 20))


_ids = itertools.count(1)


def tool_response(name: str, args: dict, text: str = "") -> LLMResponse:
    content = [{"type": "text", "text": text}] if text else []
    content.append({"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": name, "input": args})
    return LLMResponse(content=content, stop_reason="tool_use", usage=Usage(200, 30, cache_read_tokens=1000))


Step = LLMResponse | Callable[[dict], LLMResponse] | Exception


class FakeLLM:
    """Oldindan yozilgan javoblar ketma-ketligi. Callable bo'lsa, so'rov (kwargs) bilan chaqiriladi."""

    def __init__(self, steps: list[Step] | None = None, default: str = "OK") -> None:
        self.steps = list(steps or [])
        self.default = default
        self.calls: list[dict] = []

    async def chat(self, **kwargs) -> LLMResponse:
        self.calls.append(kwargs)
        if not self.steps:
            return text_response(self.default)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(kwargs) if callable(step) else step


class DownLLM:
    async def chat(self, **kwargs) -> LLMResponse:
        raise LLMUnavailable("down")


class FakeBot(Bot):
    def __init__(self) -> None:
        super().__init__("123456:TEST-TOKEN")
        self.calls: list = []
        self._msg_ids = itertools.count(1000)

    def _message(self, chat_id: int, text: str | None = None, photo: bool = False) -> Message:
        return Message(
            message_id=next(self._msg_ids),
            date=datetime.now(UTC),
            chat=Chat(id=int(chat_id), type="private"),
            text=text,
            photo=[PhotoSize(file_id=f"file_{chat_id}", file_unique_id="u", width=1, height=1)] if photo else None,
        )

    async def __call__(self, method, request_timeout=None):  # noqa: ANN001
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return self._message(method.chat_id, method.text)
        if isinstance(method, SendPhoto):
            return self._message(method.chat_id, photo=True)
        if isinstance(method, SendMediaGroup):
            return [self._message(method.chat_id, photo=True) for _ in method.media]
        return True

    def sent(self, kind=SendMessage) -> list:
        return [c for c in self.calls if isinstance(c, kind)]
