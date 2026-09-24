"""Gibrid qidiruv: pg_trgm (so'z bo'yicha, imlo xatolariga chidamli) + pgvector (ma'no bo'yicha).

Natijalar Reciprocal Rank Fusion bilan birlashtiriladi, keyin razmer/rang/narx filtrlari qo'llanadi.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Category, Product
from app.services.embeddings import EmbeddingProvider
from app.services.text import normalize

CANDIDATES = 20
RRF_K = 60
TRGM_MIN_SCORE = 0.25


async def _trigram_ids(session: AsyncSession, shop_id: int, query: str) -> list[int]:
    q = normalize(query)
    if not q:
        return []
    score = func.greatest(func.similarity(Product.search_text, q), func.word_similarity(q, Product.search_text))
    tokens = [t for t in q.split() if len(t) >= 3]
    ilike_any = [Product.search_text.ilike(f"%{t}%") for t in tokens]
    stmt = (
        select(Product.id, score.label("score"))
        .where(Product.shop_id == shop_id, Product.is_active, or_(score >= TRGM_MIN_SCORE, *ilike_any))
        .order_by(score.desc())
        .limit(CANDIDATES)
    )
    return [row.id for row in await session.execute(stmt)]


async def _vector_ids(session: AsyncSession, shop_id: int, query: str, embedder: EmbeddingProvider) -> list[int]:
    try:
        [vec] = await embedder.embed([query], input_type="query")
    except Exception:
        return []
    stmt = (
        select(Product.id)
        .where(Product.shop_id == shop_id, Product.is_active, Product.embedding.is_not(None))
        .order_by(Product.embedding.cosine_distance(vec))
        .limit(CANDIDATES)
    )
    return list(await session.scalars(stmt))


def rrf_merge(*rankings: list[int]) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores, key=lambda pid: -scores[pid])


def _attr_matches(attrs: dict, key_aliases: tuple[str, ...], wanted: str | None) -> bool:
    if not wanted:
        return True
    wanted_n = normalize(wanted)
    for key, value in (attrs or {}).items():
        if normalize(key) in key_aliases and normalize(str(value)) == wanted_n:
            return True
    return False


SIZE_KEYS = ("size", "razmer", "olcham", "razmeri")
COLOR_KEYS = ("color", "rang", "tsvet", "colour")


def product_card(product: Product, size: str | None = None, color: str | None = None) -> dict:
    variants = [
        v
        for v in product.variants
        if _attr_matches(v.attrs, SIZE_KEYS, size) and _attr_matches(v.attrs, COLOR_KEYS, color)
    ]
    return {
        "product_id": product.id,
        "name": product.name,
        "price": product.price,
        "currency": product.currency,
        "has_photos": bool(product.images),
        "variants": [
            {
                "variant_id": v.id,
                "attrs": v.attrs or {},
                "price": v.price,
                "in_stock": v.stock is None or v.stock > 0,
                "stock": v.stock,
            }
            for v in variants
        ],
    }


async def search_products(
    session: AsyncSession,
    shop_id: int,
    query: str,
    *,
    category: str | None = None,
    size: str | None = None,
    color: str | None = None,
    max_price: int | None = None,
    limit: int = 5,
    embedder: EmbeddingProvider | None = None,
) -> dict:
    rankings = [await _trigram_ids(session, shop_id, query)]
    if embedder is not None:
        rankings.append(await _vector_ids(session, shop_id, query, embedder))
    ids = rrf_merge(*rankings)
    if not ids and category:
        # So'rov umumiy bo'lsa ("nima bor?"), kategoriya bo'yicha ko'rsatamiz
        ids = list(
            await session.scalars(
                select(Product.id)
                .join(Category, Category.id == Product.category_id)
                .where(Product.shop_id == shop_id, Product.is_active, Category.name.ilike(f"%{category}%"))
                .limit(CANDIDATES)
            )
        )
    if not ids:
        return {"products": [], "note": "Katalogda mos mahsulot topilmadi"}

    products = (
        await session.scalars(
            select(Product)
            .where(Product.shop_id == shop_id, Product.id.in_(ids))
            .options(selectinload(Product.variants), selectinload(Product.images))
        )
    ).all()
    by_id = {p.id: p for p in products}
    cat_names: dict[int, str] = {}
    if category:
        cat_ids = {p.category_id for p in products if p.category_id}
        if cat_ids:
            rows = await session.execute(select(Category.id, Category.name).where(Category.id.in_(cat_ids)))
            cat_names = {r.id: r.name for r in rows}

    matched, alternatives = [], []
    for pid in ids:
        p = by_id.get(pid)
        if p is None:
            continue
        if category and p.category_id and normalize(category) not in normalize(cat_names.get(p.category_id, "")):
            continue
        card = product_card(p, size, color)
        if max_price is not None:
            card["variants"] = [v for v in card["variants"] if v["price"] <= max_price]
        if card["variants"]:
            matched.append(card)
        else:
            alternatives.append(product_card(p))
    result: dict = {"products": matched[:limit]}
    if not matched:
        result["note"] = "So'ralgan razmer/rang/narx bo'yicha mos variant yo'q"
        result["alternatives"] = alternatives[:3]
    return result
