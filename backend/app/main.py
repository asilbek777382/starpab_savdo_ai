import logging
from contextlib import asynccontextmanager

from aiogram import Bot
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from redis.asyncio import Redis

from app.ai.llm.factory import build_llm
from app.api import (
    admin,
    auth,
    catalog,
    channels,
    conversations,
    leads,
    orders,
    shops,
    stats,
    telegram_webhook,
    test_chat,
)
from app.config import get_settings
from app.runtime import Runtime, set_runtime
from app.services.embeddings import get_embedding_provider
from app.telegram.bot import build_dispatcher, setup_webhook

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    redis = Redis.from_url(s.redis_url, decode_responses=True)
    arq = await create_pool(RedisSettings.from_dsn(s.redis_url))
    bot = Bot(s.bot_token) if s.bot_token else None
    set_runtime(Runtime(redis=redis, llm=build_llm(), bot=bot, arq=arq, embedder=get_embedding_provider()))
    app.state.dispatcher = build_dispatcher()
    if bot is not None and s.bot_mode == "webhook" and s.public_base_url:
        await setup_webhook(bot, f"{s.public_base_url.rstrip('/')}/tg/webhook/{s.webhook_secret}", s.webhook_secret)
        log.info("Telegram webhook o'rnatildi")
    yield
    if bot is not None:
        await bot.session.close()
    await arq.aclose()
    await redis.aclose()
    set_runtime(None)


def create_app() -> FastAPI:
    app = FastAPI(title="Navbatchi AI", version="0.1.0", lifespan=lifespan)
    for module in (
        telegram_webhook,
        auth,
        shops,
        channels,
        catalog,
        orders,
        leads,
        conversations,
        test_chat,
        stats,
        admin,
    ):
        app.include_router(module.router)

    @app.get("/health", tags=["system"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
