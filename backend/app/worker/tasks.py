import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import get_sessionmaker
from app.models import Category, Product
from app.runtime import get_runtime
from app.services.catalog import SYNONYMS_MARKER, with_synonyms
from app.services.conversation import reply_to_conversation
from app.services.ingest import debounce_key

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
