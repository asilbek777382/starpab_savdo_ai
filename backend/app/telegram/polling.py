"""Bot polling rejimi: domen va HTTPS bo'lmagan serverlar uchun.

    python -m app.telegram.polling

Webhook o'rniga Telegram'dan update'larni o'zi so'rab oladi. Handlerlar va AI navbati webhook rejimidagi
bilan bir xil: xabarlar DB'ga yoziladi va arq worker javob beradi.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from arq import create_pool
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.ai.llm.factory import build_llm
from app.config import get_settings
from app.runtime import Runtime, set_runtime
from app.services.embeddings import get_embedding_provider
from app.telegram.bot import ALLOWED_UPDATES, build_dispatcher

log = logging.getLogger(__name__)


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    # Avval o'rnatilgan webhook bo'lsa, polling ishlamaydi — o'chiramiz
    await bot.delete_webhook(drop_pending_updates=False)
    log.info("Start polling (@%s)", get_settings().bot_username)
    await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES, handle_signals=True)


async def main() -> None:
    s = get_settings()
    if not s.bot_token:
        raise SystemExit("BOT_TOKEN berilmagan")
    redis = Redis.from_url(s.redis_url, decode_responses=True)
    arq = await create_pool(RedisSettings.from_dsn(s.redis_url))
    bot = Bot(s.bot_token)
    set_runtime(Runtime(redis=redis, llm=build_llm(), bot=bot, arq=arq, embedder=get_embedding_provider()))
    try:
        await run_polling(bot, build_dispatcher())
    finally:
        await bot.session.close()
        await arq.aclose()
        await redis.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
