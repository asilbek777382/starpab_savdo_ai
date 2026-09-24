"""Savat: conversation.cart = [{"variant_id": int, "qty": int}]. Narx har doim bazadan olinadi."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Conversation, Product, ProductVariant

MAX_QTY = 100


class CartError(Exception):
    pass


async def load_variants(session: AsyncSession, shop_id: int, ids: list[int], for_update: bool = False):
    if not ids:
        return {}
    stmt = (
        select(ProductVariant)
        .where(ProductVariant.shop_id == shop_id, ProductVariant.id.in_(ids))
        .options(selectinload(ProductVariant.product))
    )
    if for_update:
        stmt = stmt.with_for_update(of=ProductVariant)
    rows = (await session.scalars(stmt)).all()
    return {v.id: v for v in rows}


def variant_label(variant: ProductVariant) -> str:
    attrs = ", ".join(f"{v}" for v in (variant.attrs or {}).values() if v)
    return f"{variant.product.name} ({attrs})" if attrs else variant.product.name


async def cart_view(session: AsyncSession, conv: Conversation) -> dict:
    lines = conv.cart or []
    variants = await load_variants(session, conv.shop_id, [int(x["variant_id"]) for x in lines])
    items, subtotal = [], 0
    for line in lines:
        v = variants.get(int(line["variant_id"]))
        if v is None or not v.product.is_active:
            continue
        qty = int(line["qty"])
        total = v.price * qty
        subtotal += total
        items.append(
            {
                "variant_id": v.id,
                "product_id": v.product_id,
                "name": v.product.name,
                "attrs": v.attrs or {},
                "price": v.price,
                "qty": qty,
                "line_total": total,
                "in_stock": v.stock is None or v.stock >= qty,
            }
        )
    return {"items": items, "subtotal": subtotal, "currency": "UZS"}


async def update_cart(
    session: AsyncSession, conv: Conversation, action: str, variant_id: int | None = None, qty: int | None = None
) -> dict:
    cart = [dict(x) for x in (conv.cart or [])]
    if action == "clear":
        cart = []
    else:
        if variant_id is None:
            raise CartError("variant_id kerak")
        variants = await load_variants(session, conv.shop_id, [variant_id])
        variant = variants.get(variant_id)
        if variant is None or not variant.product.is_active:
            raise CartError("Bunday mahsulot varianti topilmadi")
        existing = next((x for x in cart if int(x["variant_id"]) == variant_id), None)
        if action == "remove":
            cart = [x for x in cart if int(x["variant_id"]) != variant_id]
        elif action in ("add", "set"):
            qty = int(qty or 1)
            if qty < 1 or qty > MAX_QTY:
                raise CartError(f"Miqdor 1 dan {MAX_QTY} gacha bo'lishi kerak")
            new_qty = qty + (int(existing["qty"]) if existing and action == "add" else 0)
            if variant.stock is not None and new_qty > variant.stock:
                raise CartError(f"Omborda faqat {variant.stock} dona qolgan")
            if existing:
                existing["qty"] = new_qty
            else:
                cart.append({"variant_id": variant_id, "qty": new_qty})
        else:
            raise CartError(f"Noma'lum amal: {action}")
    conv.cart = cart
    if cart and conv.stage in ("greeting", "discovery", "offering"):
        conv.stage = "cart"
    return await cart_view(session, conv)


async def active_product_count(session: AsyncSession, shop_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(Product).where(Product.shop_id == shop_id, Product.is_active)
        )
        or 0
    )
