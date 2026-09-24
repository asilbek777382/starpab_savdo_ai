"""Buyurtma yaratish: summa LLM aytganiga emas, bazaga qarab serverda hisoblanadi."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Customer, Order, Shop, ShopSettings
from app.services.cart import load_variants
from app.services.delivery import find_zone


class OrderError(Exception):
    pass


async def next_order_number(session: AsyncSession, shop_id: int) -> int:
    return int(
        await session.scalar(
            update(Shop).where(Shop.id == shop_id).values(order_seq=Shop.order_seq + 1).returning(Shop.order_seq)
        )
    )


async def create_order(
    session: AsyncSession,
    *,
    conv: Conversation,
    customer: Customer,
    settings: ShopSettings,
    name: str,
    phone: str,
    address: str,
    comment: str | None = None,
    location: dict | None = None,
    source: str = "ai",
) -> Order:
    lines = conv.cart or []
    if not lines:
        raise OrderError("Savat bo'sh")
    if not phone:
        raise OrderError("Telefon raqam noto'g'ri yoki yo'q")
    if not (address or location):
        raise OrderError("Manzil kerak")

    variants = await load_variants(session, conv.shop_id, [int(x["variant_id"]) for x in lines], for_update=True)
    items, subtotal = [], 0
    for line in lines:
        v = variants.get(int(line["variant_id"]))
        qty = int(line["qty"])
        if v is None or not v.product.is_active:
            raise OrderError("Savatdagi mahsulotlardan biri endi mavjud emas")
        if v.stock is not None and v.stock < qty:
            raise OrderError(f"{v.product.name}: omborda faqat {v.stock} dona qolgan")
        items.append(
            {
                "variant_id": v.id,
                "product_id": v.product_id,
                "name": v.product.name,
                "attrs": v.attrs or {},
                "price": v.price,
                "qty": qty,
                "line_total": v.price * qty,
            }
        )
        subtotal += v.price * qty

    zone = find_zone(settings.delivery_zones or [], address, location)
    delivery_fee = int(zone.get("fee", 0)) if zone else 0
    if not zone and settings.delivery_zones:
        comment = ((comment or "") + "\n[Yetkazish hududi aniqlanmadi — narxni sotuvchi aniqlaydi]").strip()

    for line in lines:
        v = variants[int(line["variant_id"])]
        if v.stock is not None:
            v.stock -= int(line["qty"])

    order = Order(
        shop_id=conv.shop_id,
        customer_id=customer.id,
        conversation_id=conv.id,
        number=await next_order_number(session, conv.shop_id),
        status="new",
        items=items,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=subtotal + delivery_fee,
        customer_name=name,
        phone=phone,
        address=address,
        location=location,
        comment=comment,
        source=source,
    )
    session.add(order)
    conv.cart = []
    conv.stage = "order_created"
    customer.name = customer.name or name
    customer.phone = phone
    customer.last_address = {"address": address, "location": location}
    await session.flush()
    return order


async def set_order_status(session: AsyncSession, order: Order, status: str) -> None:
    if status == order.status:
        return
    if status == "cancelled" and order.status != "cancelled":
        ids = [int(i["variant_id"]) for i in order.items]
        variants = await load_variants(session, order.shop_id, ids, for_update=True)
        for item in order.items:
            v = variants.get(int(item["variant_id"]))
            if v is not None and v.stock is not None:
                v.stock += int(item["qty"])
    order.status = status


async def get_order(session: AsyncSession, shop_id: int, order_id: int) -> Order | None:
    return await session.scalar(select(Order).where(Order.shop_id == shop_id, Order.id == order_id))
