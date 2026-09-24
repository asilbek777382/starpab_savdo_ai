"""Jarayon bo'ylab umumiy obyektlar (bot, redis, arq, LLM). API va worker startup'da o'rnatiladi."""

from dataclasses import dataclass

from aiogram import Bot
from arq.connections import ArqRedis
from redis.asyncio import Redis

from app.ai.llm.base import LLMClient
from app.services.embeddings import EmbeddingProvider


@dataclass
class Runtime:
    redis: Redis
    llm: LLMClient
    bot: Bot | None = None
    arq: ArqRedis | None = None
    embedder: EmbeddingProvider | None = None


_runtime: Runtime | None = None


def set_runtime(rt: Runtime | None) -> None:
    global _runtime
    _runtime = rt


def get_runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError("Runtime o'rnatilmagan")
    return _runtime
