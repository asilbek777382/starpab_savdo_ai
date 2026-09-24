"""Sotuvchiga xabarnomalar: yangi buyurtma, odamga uzatish, ogohlantirishlar.

Bot xabarlarni boshqa chatga forward qila olmaydi, shuning uchun sotuvchiga bot chati orqali alohida yoziladi.
"""

import html
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt import fmt_sum
from app.models import Channel, Conversation, Customer, Order, ShopUser

log = logging.getLogger(__name__)


def customer_link(customer: Customer) -> str:
    return f"https://t.me/{customer.username}" if customer.username else f"tg://user?id={customer.external_user_id}"


def order_text(order: Order, customer: Customer, test: bool = False) -> str:
    e = html.escape
    lines = [f"{'[TEST] ' if test else ''}🆕 <b>Yangi buyurtma #{order.number}</b>", ""]
    for item in order.items:
        attrs = ", ".join(str(v) for v in (item.get("attrs") or {}).values() if v)
        name = f"{item['name']} ({attrs})" if attrs else item["name"]
        lines.append(f"• {e(name)} × {item['qty']} = {fmt_sum(item['line_total'])}")
    lines += [
        "",
        f"Mahsulotlar: {fmt_sum(order.subtotal)}",
        f"Yetkazish: {fmt_sum(order.delivery_fee)}",
        f"<b>Jami: {fmt_sum(order.total)}</b>",
        "",
        f"Mijoz: {e(order.customer_name or customer.name or '-')}",
        f"Telefon: {e(order.phone or '-')}",
        f"Manzil: {e(order.address or '-')}",
    ]
    if order.comment:
        lines.append(f"Izoh: {e(order.comment)}")
    return "\n".join(lines)


def order_keyboard(order: Order, customer: Customer) -> InlineKeyboardMarkup:
    rows = []
    if order.status == "new":
        rows.append(
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ord:c:{order.id}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"ord:x:{order.id}"),
            ]
        )
    elif order.status == "confirmed":
        rows.append([InlineKeyboardButton(text="🚚 Yuborildi", callback_data=f"ord:s:{order.id}")])
    rows.append([InlineKeyboardButton(text="💬 Mijozga yozish", url=customer_link(customer))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def shop_recipients(session: AsyncSession, shop_id: int) -> list[int]:
    rows = await session.scalars(select(ShopUser.telegram_user_id).where(ShopUser.shop_id == shop_id, ShopUser.notify))
    return list(rows)


async def notify_shop(bot: Bot, session: AsyncSession, shop_id: int, text: str, markup=None) -> None:
    for chat_id in await shop_recipients(session, shop_id):
        try:
            await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        except Exception:  # noqa: BLE001 — bitta xodimga yetmasa, qolganlarga yuborishda davom etamiz
            log.warning("Sotuvchiga xabar yuborilmadi (chat=%s)", chat_id, exc_info=True)


class TelegramNotifier:
    """Xabarnomalar yig'ib boriladi va flush() da — tranzaksiya commit bo'lgandan keyin — yuboriladi,
    shunda sotuvchi saqlanmay qolgan buyurtma haqida xabar olmaydi."""

    def __init__(self, bot: Bot, session: AsyncSession, shop_id: int) -> None:
        self.bot, self.session, self.shop_id = bot, session, shop_id
        self._pending: list[tuple[str, InlineKeyboardMarkup | None, dict | None]] = []

    async def new_order(self, order: Order, customer: Customer, channel: Channel) -> None:
        test = channel.type == "test"
        self._pending.append((order_text(order, customer, test), order_keyboard(order, customer), order.location))

    async def handoff(self, conv: Conversation, customer: Customer, reason: str) -> None:
        text = (
            f"🙋 <b>Mijoz menejerni kutmoqda</b>\n"
            f"Mijoz: {html.escape(customer.name or '-')}\n"
            f"Sabab: {html.escape(reason)}\n\n"
            "AI bu suhbatda vaqtincha jim turadi."
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💬 Mijozga yozish", url=customer_link(customer))],
                [InlineKeyboardButton(text="🤖 AI'ni qayta yoqish", callback_data=f"conv:ai:{conv.id}")],
            ]
        )
        self._pending.append((text, markup, None))

    async def flush(self) -> None:
        pending, self._pending = self._pending, []
        for text, markup, location in pending:
            await notify_shop(self.bot, self.session, self.shop_id, text, markup)
            if location:
                for chat_id in await shop_recipients(self.session, self.shop_id):
                    try:
                        await self.bot.send_location(chat_id, location["latitude"], location["longitude"])
                    except Exception:  # noqa: BLE001
                        log.warning("Lokatsiya yuborilmadi", exc_info=True)
