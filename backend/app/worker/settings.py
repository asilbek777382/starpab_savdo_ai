import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.ai.llm.factory import build_llm
from app.config import get_settings
from app.runtime import Runtime, get_runtime, set_runtime
from app.services.embeddings import get_embedding_provider
from app.worker.tasks import enrich_product, process_conversation

logging.basicConfig(level=logging.INFO)


async def startup(ctx: dict) -> None:
    s = get_settings()
    bot = Bot(s.bot_token, default=DefaultBotProperties()) if s.bot_token else None
    set_runtime(
        Runtime(
            redis=Redis.from_url(s.redis_url, decode_responses=True),
            llm=build_llm(),
            bot=bot,
            arq=ctx["redis"],
            embedder=get_embedding_provider(),
        )
    )


async def shutdown(ctx: dict) -> None:
    rt = get_runtime()
    if rt.bot is not None:
        await rt.bot.session.close()
    await rt.redis.aclose()


class WorkerSettings:
    functions = [process_conversation, enrich_product]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 20
    job_timeout = 300
