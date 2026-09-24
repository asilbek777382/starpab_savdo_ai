from aiogram.methods import DeleteWebhook

from app.telegram.bot import ALLOWED_UPDATES, build_dispatcher
from app.telegram.polling import run_polling


async def test_run_polling_deletes_webhook_and_starts(fake_bot, monkeypatch):
    dp = build_dispatcher()
    started = {}

    async def fake_start_polling(bot, **kwargs):
        started["bot"] = bot
        started.update(kwargs)

    monkeypatch.setattr(dp, "start_polling", fake_start_polling)
    await run_polling(fake_bot, dp)
    assert any(isinstance(c, DeleteWebhook) for c in fake_bot.calls)
    assert started["bot"] is fake_bot and started["allowed_updates"] == ALLOWED_UPDATES
    assert "business_message" in started["allowed_updates"]
