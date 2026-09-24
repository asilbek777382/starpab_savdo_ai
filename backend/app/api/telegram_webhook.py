import hmac
import logging

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings
from app.runtime import get_runtime
from app.services.dedup import is_duplicate_update

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/tg/webhook/{secret}", include_in_schema=False)
async def telegram_webhook(
    secret: str,
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict:
    expected = get_settings().webhook_secret
    if not (hmac.compare_digest(secret, expected) and hmac.compare_digest(x_telegram_bot_api_secret_token, expected)):
        raise HTTPException(403)
    rt = get_runtime()
    data = await request.json()
    update_id = data.get("update_id")
    if update_id is not None and await is_duplicate_update(rt.redis, int(update_id)):
        return {"ok": True, "duplicate": True}
    dp = request.app.state.dispatcher
    try:
        update = Update.model_validate(data, context={"bot": rt.bot})
        await dp.feed_update(rt.bot, update)
    except Exception:
        # Telegram qayta-qayta yubormasligi uchun baribir 200 qaytaramiz; xato logda
        log.exception("Update qayta ishlanmadi: %s", update_id)
    return {"ok": True}
