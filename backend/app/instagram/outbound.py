import logging

from redis.asyncio import Redis

from app.instagram.client import InstagramAPI

log = logging.getLogger(__name__)

SENT_TTL = 24 * 3600


def sent_key(mid: str) -> str:
    return f"ig:sent:{mid}"


class InstagramOutbound:
    """Instagram Direct orqali mijozga yuborish.

    Yuborilgan xabar Meta'dan is_echo sifatida qaytib keladi: o'zimiz yuborganlarini sotuvchi yozgan xabardan
    ajratish uchun message_id'lar Redis'da eslab qolinadi.
    """

    supports_telegram_file_ids = False

    def __init__(self, api: InstagramAPI, recipient_id: str, redis: Redis) -> None:
        self.api, self.recipient_id, self.redis = api, recipient_id, redis

    async def _remember(self, mids: list[str | None]) -> None:
        for mid in mids:
            if mid:
                await self.redis.set(sent_key(mid), 1, ex=SENT_TTL)

    async def send_text(self, text: str) -> int | None:
        await self._remember(await self.api.send_text(self.recipient_id, text))
        return None  # Instagram message_id raqam emas — Message.external_message_id bo'sh qoladi

    async def send_photos(self, photos: list[str], caption: str | None = None) -> list[str | None]:
        mids = []
        for url in photos:
            if url.startswith(("http://", "https://")):
                mids.append(await self.api.send_image(self.recipient_id, url))
        await self._remember(mids)
        if caption:
            await self.send_text(caption)
        return [None] * len(photos)

    async def send_typing(self) -> None:
        try:
            await self.api.typing(self.recipient_id)
        except Exception:  # noqa: BLE001 — "yozmoqda" holati muhim emas
            log.debug("Instagram typing yuborilmadi", exc_info=True)
