import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import get_sessionmaker
from app.instagram import client as ig
from app.models import Category, Channel, Product
from app.runtime import get_runtime
from app.services.catalog import SYNONYMS_MARKER, with_synonyms
from app.services.conversation import reply_to_conversation
from app.services.crypto import decrypt, encrypt
from app.services.ingest import debounce_key
from app.telegram.notify import notify_shop

log = logging.getLogger(__name__)

SYNONYMS_PROMPT = (
    "Sen o'zbek onlayn do'koni uchun qidiruv sinonimlarini yozasan. Mahsulot uchun mijozlar yozishi mumkin "
    "bo'lgan 10-20 ta so'z va iborani ber: o'zbek lotin, o'zbek kirill va rus tilida, ko'p uchraydigan imlo "
    "xatolari va ruscha translit (masalan: ko'ylak, кўйлак, платье, platye, koylak). Faqat vergul bilan ajratilgan "
    "ro'yxatni yoz."
)


async def process_conversation(ctx: dict, conv_id: int, token: str) -> str:
    rt = get_runtime()
    if await rt.redis.get(debounce_key(conv_id)) != token:
        return "superseded"  # keyinroq kelgan xabar uchun alohida job javob beradi
    async with rt.redis.lock(f"lock:conv:{conv_id}", timeout=180, blocking_timeout=120):
        async with get_sessionmaker()() as session:
            result = await reply_to_conversation(session, rt, conv_id)
    return result.status


async def enrich_product(ctx: dict, product_id: int) -> str:
    """search_text'ga sinonimlar qo'shadi va (sozlangan bo'lsa) embedding hisoblaydi."""
    rt = get_runtime()
    async with get_sessionmaker()() as session:
        product = await session.scalar(
            select(Product).where(Product.id == product_id).options(selectinload(Product.variants))
        )
        if product is None:
            return "missing"
        category = await session.get(Category, product.category_id) if product.category_id else None
        info = f"Nomi: {product.name}\nKategoriya: {category.name if category else '-'}\nTavsif: {product.description}"
        synonyms = ""
        try:
            resp = await rt.llm.chat(
                system=SYNONYMS_PROMPT,
                messages=[{"role": "user", "content": [{"type": "text", "text": info}]}],
                max_tokens=400,
            )
            synonyms = resp.text
        except Exception:  # noqa: BLE001
            log.warning("Sinonimlar yaratilmadi (product=%s)", product_id, exc_info=True)
        base = product.search_text.split(SYNONYMS_MARKER)[0]
        product.search_text = with_synonyms(base, synonyms)
        if rt.embedder is not None:
            try:
                [vec] = await rt.embedder.embed([f"{info}\n{synonyms}"], input_type="document")
                product.embedding = vec
            except Exception:  # noqa: BLE001
                log.warning("Embedding hisoblanmadi (product=%s)", product_id, exc_info=True)
        await session.commit()
    return "ok"


REFRESH_BEFORE = timedelta(days=10)


async def refresh_instagram_tokens(ctx: dict) -> str:
    """Instagram long-lived tokenlari ~60 kun yashaydi: 10 kun qolganda yangilanadi."""
    rt = get_runtime()
    refreshed = failed = 0
    async with get_sessionmaker()() as session:
        channels = await session.scalars(
            select(Channel).where(
                Channel.type == "instagram",
                Channel.is_enabled,
                Channel.token_encrypted.is_not(None),
                Channel.token_expires_at < datetime.now(UTC) + REFRESH_BEFORE,
            )
        )
        for channel in channels:
            try:
                token = await ig.refresh_token(decrypt(channel.token_encrypted) or "")
            except ig.InstagramError:
                failed += 1
                log.warning("Instagram token yangilanmadi (channel=%s)", channel.id, exc_info=True)
                if rt.bot is not None and await rt.redis.set(f"warn:{channel.shop_id}:igtoken", 1, nx=True, ex=86400):
                    await notify_shop(rt.bot, session, channel.shop_id, IG_RECONNECT)
                continue
            channel.token_encrypted = encrypt(token.access_token)
            channel.token_expires_at = token.expires_at
            refreshed += 1
        await session.commit()
    return f"refreshed={refreshed} failed={failed}"


IG_RECONNECT = "⚠️ Instagram ulanishi muddati tugayapti. Panel → Ulash → Instagram'ni qayta ulang."
