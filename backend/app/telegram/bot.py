from functools import lru_cache

from aiogram import Bot, Dispatcher

from app.telegram.handlers import router

ALLOWED_UPDATES = [
    "message",
    "callback_query",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]


@lru_cache
def build_dispatcher() -> Dispatcher:
    """Router faqat bitta dispatcher'ga ulanadi, shuning uchun yagona nusxa."""
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def setup_webhook(bot: Bot, url: str, secret: str) -> None:
    await bot.set_webhook(url, secret_token=secret, allowed_updates=ALLOWED_UPDATES, drop_pending_updates=False)
