"""Tashlab ketilgan savat eslatmasi.

Mijoz savatga mahsulot qo'shib, buyurtma bermasdan jim qolsa (sozlamadagi N soat), unga bitta eslatma yuboriladi:
savatdagi mahsulotlar va narxlar (bazadan), "buyurtmani rasmiylashtiraymi?" savoli. Mijoz qayta yozib, yana jim qolsa —
yana bitta. 22 soatdan eski suhbatlarga yozilmaydi (Instagram 24 soatlik oynasi va bezovta qilmaslik uchun).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt import fmt_sum
from app.models import Channel, Conversation, Customer, Message, Shop, ShopSettings
from app.runtime import Runtime
from app.services.cart import cart_view
from app.services.handoff import detect_script
from app.services.outbound import build_outbound, within_messaging_window
from app.services.usage import check_limits

log = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=22)
BATCH = 200

TEXTS = {
    "uz": {
        "hello": "Assalomu alaykum{name}! Savatingizda tanlagan mahsulotlaringiz turibdi:",
        "total": "Jami",
        "ask": "Buyurtmani rasmiylashtirib beraymi? Savollaringiz bo'lsa, bemalol yozing 🙂",
    },
    "uz_cyrl": {
        "hello": "Ассалому алайкум{name}! Саватингизда танлаган маҳсулотларингиз турибди:",
        "total": "Жами",
        "ask": "Буюртмани расмийлаштириб берайми? Саволларингиз бўлса, бемалол ёзинг 🙂",
    },
    "ru": {
        "hello": "Здравствуйте{name}! В вашей корзине остались выбранные товары:",
        "total": "Итого",
        "ask": "Оформить заказ? Если есть вопросы — пишите, с радостью помогу 🙂",
    },
}


@dataclass
class ReminderResult:
    status: str


def _sum(amount: int, lang: str) -> str:
    text = fmt_sum(amount)
    return text.replace("so'm", "сум") if lang == "ru" else text.replace("so'm", "сўм") if lang == "uz_cyrl" else text


def reminder_text(cart: dict, lang: str, name: str | None) -> str:
    t = TEXTS.get(lang, TEXTS["uz"])
    first = (name or "").split()[0] if name else ""
    lines = [t["hello"].format(name=f", {first}" if first else ""), ""]
    for item in cart["items"]:
        attrs = ", ".join(str(v) for v in (item.get("attrs") or {}).values() if v)
        title = f"{item['name']} ({attrs})" if attrs else item["name"]
        lines.append(f"• {title} × {item['qty']} — {_sum(item['line_total'], lang)}")
    lines += [f"{t['total']}: {_sum(cart['subtotal'], lang)}", "", t["ask"]]
    return "\n".join(lines)


async def due_conversations(session: AsyncSession, now: datetime | None = None) -> list[int]:
    now = now or datetime.now(UTC)
    idle_for = func.make_interval(0, 0, 0, 0, ShopSettings.cart_reminder_hours)
    rows = await session.scalars(
        select(Conversation.id)
        .join(ShopSettings, ShopSettings.shop_id == Conversation.shop_id)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(
            ShopSettings.cart_reminder_enabled,
            ShopSettings.ai_enabled,
            Channel.is_enabled,
            Channel.type != "test",
            Conversation.status == "ai",
            func.jsonb_array_length(Conversation.cart) > 0,
            Conversation.last_message_at <= now - idle_for,
            Conversation.last_message_at > now - MAX_AGE,
            or_(Conversation.cart_reminded_at.is_(None), Conversation.cart_reminded_at < Conversation.last_message_at),
        )
        .order_by(Conversation.last_message_at)
        .limit(BATCH)
    )
    return list(rows)


async def _language(session: AsyncSession, conv: Conversation, customer: Customer) -> str:
    last = await session.scalar(
        select(Message.content)
        .where(Message.conversation_id == conv.id, Message.role == "customer", Message.content != "")
        .order_by(Message.id.desc())
        .limit(1)
    )
    if last:
        return detect_script(last)
    return "ru" if (customer.language or "").startswith("ru") else "uz"


async def send_cart_reminder(session: AsyncSession, rt: Runtime, conv_id: int) -> ReminderResult:
    """Shartlarni qulf ostida qayta tekshirib, eslatma yuboradi. Har qanday natijada qayta urinilmaydi."""
    conv = await session.get(Conversation, conv_id, with_for_update=True)
    if conv is None:
        return ReminderResult("missing")
    if conv.status != "ai" or not conv.cart:
        return ReminderResult("skip")
    if conv.cart_reminded_at and conv.last_message_at and conv.cart_reminded_at >= conv.last_message_at:
        return ReminderResult("already")
    shop = await session.get(Shop, conv.shop_id)
    channel = await session.get(Channel, conv.channel_id)
    customer = await session.get(Customer, conv.customer_id)

    def done(status: str) -> ReminderResult:
        conv.cart_reminded_at = datetime.now(UTC)
        return ReminderResult(status)

    ok, _ = await check_limits(session, shop)
    if not ok:
        result = done("blocked")
    elif (channel.type == "tg_business" and not channel.can_reply) or not within_messaging_window(channel, conv):
        result = done("cannot_reply")
    else:
        cart = await cart_view(session, conv)
        cart["items"] = [i for i in cart["items"] if i["in_stock"]]
        cart["subtotal"] = sum(i["line_total"] for i in cart["items"])
        outbound = build_outbound(rt, channel, customer)
        if not cart["items"]:
            result = done("empty")
        elif outbound is None:
            result = done("no_outbound")
        else:
            text = reminder_text(cart, await _language(session, conv, customer), customer.name)
            try:
                ext_id = await outbound.send_text(text)
            except Exception:  # noqa: BLE001 — mijoz botni bloklagan bo'lishi mumkin; qayta urinmaymiz
                log.warning("Savat eslatmasi yuborilmadi (conv=%s)", conv.id, exc_info=True)
                result = done("send_failed")
            else:
                session.add(
                    Message(
                        shop_id=conv.shop_id,
                        conversation_id=conv.id,
                        role="ai",
                        content=text,
                        media={"type": "cart_reminder"},
                        external_message_id=ext_id if isinstance(ext_id, int) else None,
                        answered=True,
                    )
                )
                result = done("sent")
    await session.commit()
    return result
