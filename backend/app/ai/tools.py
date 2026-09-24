"""AI toollari. Har bir tool faqat joriy do'kon (shop_id) va joriy suhbat doirasida ishlaydi."""

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.ai.turn import TurnContext
from app.services import cart as cart_svc
from app.services.catalog import load_product
from app.services.delivery import delivery_info
from app.services.handoff import handoff_event, mark_handoff
from app.services.leads import save_lead
from app.services.orders import OrderError, create_order
from app.services.search import product_card, search_products

log = logging.getLogger(__name__)

MAX_PHOTOS = 5


class SearchProductsIn(BaseModel):
    query: str = Field(max_length=200)
    category: str | None = None
    size: str | None = None
    color: str | None = None
    max_price: int | None = Field(default=None, ge=0)


class GetProductIn(BaseModel):
    product_id: int


class SendPhotosIn(BaseModel):
    product_id: int
    caption: str | None = Field(default=None, max_length=500)


class UpdateCartIn(BaseModel):
    action: Literal["add", "remove", "set", "clear"]
    variant_id: int | None = None
    qty: int | None = None


class DeliveryIn(BaseModel):
    address: str | None = None


class CreateOrderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=40)
    address: str = Field(default="", max_length=500)
    comment: str | None = Field(default=None, max_length=500)
    customer_confirmed: bool


class SaveLeadIn(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=200)
    interest: str = Field(default="", max_length=500)
    note: str | None = Field(default=None, max_length=500)


class HandoffIn(BaseModel):
    reason: str = Field(max_length=300)


TOOLS: list[dict] = [
    {
        "name": "search_products",
        "description": "Katalogdan mahsulot qidiradi. 5 tagacha mahsulot qaytaradi: id, nom, narx, variantlar "
        "(variant_id, razmer/rang, narx, qoldiq). Mijoz mahsulot, narx yoki mavjudlik haqida so'raganda chaqir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Mijoz so'zlari bilan qidiruv matni"},
                "category": {"type": "string"},
                "size": {"type": "string", "description": "Razmer, masalan 42 yoki M"},
                "color": {"type": "string"},
                "max_price": {"type": "integer", "description": "So'mda eng yuqori narx"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product",
        "description": "Mahsulot haqida to'liq ma'lumot: tavsif, barcha variantlar, qoldiq, rasmlar soni.",
        "input_schema": {
            "type": "object",
            "properties": {"product_id": {"type": "integer"}},
            "required": ["product_id"],
        },
    },
    {
        "name": "send_product_photos",
        "description": "Mahsulot rasmlarini mijozga yuboradi (server tomonda). Rasm mijozga shu zahoti boradi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer"},
                "caption": {"type": "string", "description": "Rasm ostidagi qisqa matn (nom va narx)"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "update_cart",
        "description": "Savatni o'zgartiradi. add — qo'shish, set — miqdorni belgilash, remove — olib tashlash, "
        "clear — tozalash. Yangilangan savat va summani qaytaradi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "remove", "set", "clear"]},
                "variant_id": {"type": "integer"},
                "qty": {"type": "integer", "minimum": 1},
            },
            "required": ["action"],
        },
    },
    {
        "name": "get_delivery_info",
        "description": "Manzil (yoki mijoz yuborgan lokatsiya) bo'yicha yetkazib berish hududi, narxi va muddati.",
        "input_schema": {
            "type": "object",
            "properties": {"address": {"type": "string"}},
        },
    },
    {
        "name": "create_order",
        "description": "Savatdagi mahsulotlardan buyurtma yaratadi va sotuvchiga yuboradi. Faqat mijoz tarkib, "
        "summa va manzilni tasdiqlagandan keyin chaqir. Summa serverda hisoblanadi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "phone": {"type": "string", "description": "Telefon yoki [PHONE_1] kabi belgi"},
                "address": {"type": "string", "description": "Manzil matni (lokatsiya yuborilgan bo'lsa ham)"},
                "comment": {"type": "string"},
                "customer_confirmed": {"type": "boolean", "description": "Mijoz aniq tasdiqladimi"},
            },
            "required": ["name", "phone", "address", "customer_confirmed"],
        },
    },
    {
        "name": "save_lead",
        "description": "Mijozning telefon raqamini va nimaga qiziqqanini saqlab, operatorga (sotuvchining "
        "Telegram'iga) yuboradi. Mijoz raqamini bergan zahoti chaqir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Telefon yoki [PHONE_1] kabi belgi"},
                "name": {"type": "string"},
                "interest": {"type": "string", "description": "Mijoz nimaga qiziqdi (mahsulot, savol)"},
                "note": {"type": "string", "description": "Operator uchun qo'shimcha izoh"},
            },
            "required": ["phone", "interest"],
        },
    },
    {
        "name": "handoff_to_human",
        "description": "Suhbatni sotuvchiga (odamga) uzatadi. Shundan keyin AI bu suhbatda javob bermaydi.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]


async def _search_products(ctx: TurnContext, a: SearchProductsIn) -> dict:
    result = await search_products(
        ctx.session,
        ctx.shop.id,
        a.query,
        category=a.category,
        size=a.size,
        color=a.color,
        max_price=a.max_price,
        embedder=ctx.embedder,
    )
    if result["products"] and ctx.conv.stage in ("greeting", "discovery"):
        ctx.conv.stage = "offering"
    return result


async def _get_product(ctx: TurnContext, a: GetProductIn) -> dict:
    product = await load_product(ctx.session, ctx.shop.id, a.product_id)
    if product is None or not product.is_active:
        return {"error": "Mahsulot topilmadi"}
    card = product_card(product)
    card["description"] = product.description
    card["photos"] = len(product.images)
    return card


async def _send_photos(ctx: TurnContext, a: SendPhotosIn) -> dict:
    product = await load_product(ctx.session, ctx.shop.id, a.product_id)
    if product is None or not product.is_active:
        return {"error": "Mahsulot topilmadi"}
    images = product.images[:MAX_PHOTOS]
    if not images:
        return {"sent": 0, "note": "Bu mahsulotning rasmi yo'q"}
    file_ids = await ctx.outbound.send_photos([img.telegram_file_id or img.url for img in images], a.caption)
    for img, fid in zip(images, file_ids, strict=False):
        if fid and not img.telegram_file_id:
            img.telegram_file_id = fid  # keyingi safar qayta yuklamaslik uchun
    return {"sent": len(images)}


async def _update_cart(ctx: TurnContext, a: UpdateCartIn) -> dict:
    try:
        return await cart_svc.update_cart(ctx.session, ctx.conv, a.action, a.variant_id, a.qty)
    except cart_svc.CartError as exc:
        return {"error": str(exc), "cart": await cart_svc.cart_view(ctx.session, ctx.conv)}


async def _delivery(ctx: TurnContext, a: DeliveryIn) -> dict:
    return delivery_info(ctx.settings.delivery_zones or [], a.address, (ctx.conv.contact or {}).get("location"))


async def _create_order(ctx: TurnContext, a: CreateOrderIn) -> dict:
    if not a.customer_confirmed:
        ctx.conv.stage = "confirm"
        return {"error": "Avval mijozdan buyurtmani tasdiqlashini so'ra"}
    if ctx.order is not None:
        return {"error": "Bu javobda buyurtma allaqachon yaratildi", "order_number": ctx.order.number}
    phone = ctx.masker.unmask(a.phone)
    if not phone:
        return {"error": "Telefon raqam noto'g'ri. Mijozdan +998 XX XXX XX XX ko'rinishida so'ra"}
    try:
        order = await create_order(
            ctx.session,
            conv=ctx.conv,
            customer=ctx.customer,
            settings=ctx.settings,
            name=a.name,
            phone=phone,
            address=a.address,
            comment=a.comment,
            location=(ctx.conv.contact or {}).get("location"),
            source=ctx.order_source,
        )
    except OrderError as exc:
        return {"error": str(exc)}
    ctx.order = order
    await ctx.notifier.new_order(order, ctx.customer, ctx.channel)
    return {
        "order_number": order.number,
        "items": [{"name": i["name"], "attrs": i["attrs"], "qty": i["qty"], "price": i["price"]} for i in order.items],
        "subtotal": order.subtotal,
        "delivery_fee": order.delivery_fee,
        "total": order.total,
        "note": "Buyurtma sotuvchiga yuborildi. Mijozga raqam va summani ayt, sotuvchi tez orada bog'lanadi.",
    }


async def _save_lead(ctx: TurnContext, a: SaveLeadIn) -> dict:
    phone = ctx.masker.unmask(a.phone)
    if not phone:
        return {"error": "Telefon raqam noto'g'ri. Mijozdan +998 XX XXX XX XX ko'rinishida so'ra"}
    lead, created = await save_lead(
        ctx.session,
        conv=ctx.conv,
        customer=ctx.customer,
        channel=ctx.channel,
        settings=ctx.settings,
        phone=phone,
        name=a.name,
        interest=a.interest,
        note=a.note,
    )
    ctx.lead = lead
    if created:
        await ctx.notifier.new_lead(lead, ctx.customer, ctx.conv)
    if ctx.settings.handoff_after_lead:
        ctx.handed_off = True
        return {"ok": True, "note": "Mijozga rahmat ayt: operator tez orada shu raqamga bog'lanadi."}
    return {"ok": True, "note": "Raqam operatorga yuborildi. Suhbatni davom ettir."}


async def _handoff(ctx: TurnContext, a: HandoffIn) -> dict:
    if not ctx.handed_off:
        mark_handoff(ctx.conv, ctx.settings)
        ctx.handed_off = True
        ctx.session.add(handoff_event(ctx.conv, a.reason))
        await ctx.notifier.handoff(ctx.conv, ctx.customer, a.reason)
    return {"ok": True, "note": "Mijozga savoli menejerga yuborilganini qisqa ayt."}


HANDLERS = {
    "search_products": (SearchProductsIn, _search_products),
    "get_product": (GetProductIn, _get_product),
    "send_product_photos": (SendPhotosIn, _send_photos),
    "update_cart": (UpdateCartIn, _update_cart),
    "get_delivery_info": (DeliveryIn, _delivery),
    "create_order": (CreateOrderIn, _create_order),
    "save_lead": (SaveLeadIn, _save_lead),
    "handoff_to_human": (HandoffIn, _handoff),
}

# Lid rejimida savat va buyurtma toollari berilmaydi
LEAD_MODE_EXCLUDED = {"update_cart", "create_order"}


def tools_for_mode(mode: str) -> list[dict]:
    if mode == "lead":
        return [t for t in TOOLS if t["name"] not in LEAD_MODE_EXCLUDED]
    return TOOLS


async def execute_tool(ctx: TurnContext, name: str, raw_input: dict) -> tuple[str, bool]:
    """Qaytaradi: (tool_result matni JSON, is_error)."""
    entry = HANDLERS.get(name)
    if entry is None or (ctx.settings.ai_mode == "lead" and name in LEAD_MODE_EXCLUDED):
        return json.dumps({"error": f"Noma'lum tool: {name}"}), True
    model, handler = entry
    try:
        args = model.model_validate(raw_input or {})
    except ValidationError as exc:
        details = exc.errors(include_url=False)
        return json.dumps({"error": "Noto'g'ri parametrlar", "details": details}, default=str), True
    try:
        # Savepoint: tool ichida xato bo'lsa, faqat uning o'zgarishlari bekor qilinadi
        async with ctx.session.begin_nested():
            result = await handler(ctx, args)
    except Exception:
        log.exception("Tool xatosi: %s", name)
        return json.dumps({"error": "Ichki xato, keyinroq urinib ko'ring"}), True
    ctx.tool_log.append({"tool": name, "input": raw_input, "result": result})
    return json.dumps(result, ensure_ascii=False, default=str), "error" in result
