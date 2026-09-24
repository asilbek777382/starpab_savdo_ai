"""Katalog: mahsulotni saqlash va qidiruv matnini (search_text) tayyorlash."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Category, Product, ProductImage, ProductVariant
from app.services.text import normalize

SYNONYMS_MARKER = " | "


def base_search_text(product: Product, category_name: str | None, variants: list[dict]) -> str:
    parts = [product.name, product.description or "", category_name or ""]
    for attrs in variants:
        parts.extend(str(v) for v in (attrs or {}).values())
    return normalize(" ".join(parts))


def with_synonyms(base: str, synonyms: str) -> str:
    syn = normalize(synonyms)
    return f"{base}{SYNONYMS_MARKER}{syn}" if syn else base


async def get_or_create_category(session: AsyncSession, shop_id: int, name: str | None) -> Category | None:
    name = (name or "").strip()
    if not name:
        return None
    cat = await session.scalar(select(Category).where(Category.shop_id == shop_id, Category.name.ilike(name)))
    if cat is None:
        cat = Category(shop_id=shop_id, name=name)
        session.add(cat)
        await session.flush()
    return cat


async def load_product(session: AsyncSession, shop_id: int, product_id: int) -> Product | None:
    return await session.scalar(
        select(Product)
        .where(Product.shop_id == shop_id, Product.id == product_id)
        .options(selectinload(Product.variants), selectinload(Product.images))
    )


async def save_product(
    session: AsyncSession,
    shop_id: int,
    *,
    product: Product | None,
    name: str,
    price: int,
    description: str = "",
    category_name: str | None = None,
    category_id: int | None = None,
    is_active: bool = True,
    variants: list[dict] | None = None,
    images: list[str] | None = None,
) -> Product:
    """variants: [{"attrs": {...}, "sku": ..., "price_override": ..., "stock": ...}]. Bo'sh bo'lsa bitta
    standart variant yaratiladi (savat har doim variant bilan ishlaydi).

    Mavjud mahsulot load_product() bilan (variants/images yuklangan holda) berilishi kerak."""
    category = None
    if category_id is not None:
        category = await session.scalar(select(Category).where(Category.shop_id == shop_id, Category.id == category_id))
    elif category_name:
        category = await get_or_create_category(session, shop_id, category_name)

    if product is None:
        product = Product(shop_id=shop_id, name=name, price=price, variants=[], images=[])
        session.add(product)
    product.name = name
    product.price = price
    product.description = description or ""
    product.category_id = category.id if category else None
    product.is_active = is_active
    product.embedding = None  # matn o'zgardi — qayta hisoblanadi

    variants = variants or [{"attrs": {}}]
    product.variants = [
        ProductVariant(
            shop_id=shop_id,
            sku=v.get("sku"),
            attrs={k: str(val) for k, val in (v.get("attrs") or {}).items() if val not in (None, "")},
            price_override=v.get("price_override"),
            stock=v.get("stock"),
        )
        for v in variants
    ]
    if images is not None:
        product.images = [ProductImage(shop_id=shop_id, url=url, sort=i) for i, url in enumerate(images)]
    category_name = category.name if category else None
    product.search_text = base_search_text(product, category_name, [v.attrs for v in product.variants])
    await session.flush()
    return product
