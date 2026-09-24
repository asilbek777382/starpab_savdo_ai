import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, CallbackQuery
from aiogram.types import Message as TgMessage
from sqlalchemy import select

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import Account, Channel, Conversation, Customer, Lead, Message, Order, Shop, ShopSettings, ShopUser
from app.runtime import get_runtime
from app.services import auth as auth_svc
from app.services.ingest import (
    enqueue_reply,
    get_open_conversation,
    get_or_create_customer,
    ingest_customer_message,
    ingest_staff_message,
)
from app.services.orders import set_order_status
from app.services.shops import create_shop, get_channel, shops_of_user
from app.services.usage import check_limits, current_usage
from app.telegram import texts
from app.telegram.notify import order_keyboard, order_text
from app.telegram.outbound import TelegramOutbound

log = logging.getLogger(__name__)
router = Router(name="main")


def bot_link(shop_id: int) -> str:
    return f"https://t.me/{get_settings().bot_username}?start=shop_{shop_id}"


# ---------- Telegram Business ----------


@router.business_connection()
async def on_business_connection(conn: BusinessConnection, bot: Bot) -> None:
    can_reply = bool(conn.rights.can_reply) if conn.rights else bool(conn.can_reply)
    async with get_sessionmaker()() as session:
        channel = await session.scalar(select(Channel).where(Channel.business_connection_id == conn.id))
        if channel is None:
            shops = await shops_of_user(session, conn.user.id)
            if shops:
                shop = shops[0][0]
            else:
                shop = await create_shop(session, conn.user.id, conn.user.full_name, f"{conn.user.full_name} do'koni")
            channel = Channel(shop_id=shop.id, type="tg_business", business_connection_id=conn.id)
            session.add(channel)
        else:
            shop = await session.get(Shop, channel.shop_id)
        channel.owner_user_id = conn.user.id
        channel.external_id = str(conn.user.id)
        channel.can_reply = can_reply
        channel.is_enabled = conn.is_enabled
        await session.commit()

    if not conn.is_enabled:
        text = texts.BUSINESS_DISCONNECTED
    elif not can_reply:
        text = texts.BUSINESS_NO_REPLY
    else:
        text = texts.BUSINESS_CONNECTED.format(shop=shop.name)
    try:
        await bot.send_message(conn.user_chat_id, text, parse_mode="HTML")
    except Exception:  # noqa: BLE001
        log.warning("Business ulanish xabari yuborilmadi", exc_info=True)


@router.business_message()
async def on_business_message(message: TgMessage) -> None:
    if message.sender_business_bot is not None:
        return  # bizning bot yuborgan xabar
    rt = get_runtime()
    async with get_sessionmaker()() as session:
        channel = await session.scalar(
            select(Channel).where(Channel.business_connection_id == message.business_connection_id)
        )
        if channel is None or not channel.is_enabled:
            return
        if message.from_user and message.from_user.id == channel.owner_user_id:
            await ingest_staff_message(session, channel, message)
            await session.commit()
            return
        conv = await ingest_customer_message(session, rt, channel, message)
        await session.commit()
    if conv is not None:
        await enqueue_reply(rt, conv.id)


@router.edited_business_message()
async def on_edited_business_message(message: TgMessage) -> None:
    async with get_sessionmaker()() as session:
        msg = await session.scalar(
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(Customer, Customer.id == Conversation.customer_id)
            .join(Channel, Channel.id == Customer.channel_id)
            .where(
                Channel.business_connection_id == message.business_connection_id,
                Customer.chat_id == message.chat.id,
                Message.external_message_id == message.message_id,
            )
        )
        if msg is not None and not msg.answered:
            msg.content = message.text or message.caption or msg.content
            await session.commit()


@router.deleted_business_messages()
async def on_deleted_business_messages(event: BusinessMessagesDeleted) -> None:
    log.info("Business xabarlar o'chirildi: chat=%s ids=%s", event.chat.id, event.message_ids)


# ---------- Oddiy bot chati: sotuvchi va "bot rejimi" mijozlari ----------


def active_shop_key(tg_user_id: int) -> str:
    return f"botshop:{tg_user_id}"


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("link_")))
async def on_link_telegram(message: TgMessage, command: CommandObject) -> None:
    """Saytdagi "Telegram'ni ulash" tugmasi: akkauntga shu Telegram bog'lanadi."""
    rt = get_runtime()
    account_id = await auth_svc.consume_token(rt.redis, "tglink", command.args.removeprefix("link_"))
    if account_id is None:
        await message.answer(texts.LINK_EXPIRED)
        return
    async with get_sessionmaker()() as session:
        account = await session.get(Account, int(account_id))
        if account is None:
            await message.answer(texts.LINK_EXPIRED)
            return
        try:
            await auth_svc.link_telegram(session, account, message.from_user.id)
        except auth_svc.AuthError as exc:
            await message.answer(f"⚠️ {exc}")
            return
        await session.commit()
    await message.answer(texts.LINK_OK)


@router.message(Command("web"))
async def on_web_login(message: TgMessage) -> None:
    """Bir martalik havola: botda ro'yxatdan o'tgan sotuvchi saytga parolsiz kiradi."""
    if message.chat.type != "private":
        return
    async with get_sessionmaker()() as session:
        if not await shops_of_user(session, message.from_user.id):
            await message.answer("Sizda do'kon yo'q. /start bosing.")
            return
    url = await auth_svc.issue_magic_link(get_runtime().redis, message.from_user.id, message.from_user.full_name)
    await message.answer(texts.WEB_LINK.format(url=url), disable_web_page_preview=True)


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("shop_")))
async def on_customer_start(message: TgMessage, command: CommandObject) -> None:
    try:
        shop_id = int(command.args.removeprefix("shop_"))
    except ValueError:
        await message.answer(texts.CUSTOMER_NO_SHOP)
        return
    async with get_sessionmaker()() as session:
        shop = await session.get(Shop, shop_id)
        if shop is None:
            await message.answer(texts.CUSTOMER_NO_SHOP)
            return
        channel = await get_channel(session, shop.id, "tg_bot")
        customer = await get_or_create_customer(session, channel, message.from_user, message.chat.id)
        await get_open_conversation(session, customer)
        await session.commit()
    # Mijoz bir nechta do'kon havolasidan kirgan bo'lishi mumkin: oxirgi tanlangani faol
    await get_runtime().redis.set(active_shop_key(message.from_user.id), customer.id)
    await message.answer(texts.CUSTOMER_WELCOME.format(shop=shop.name))


@router.message(CommandStart())
async def on_seller_start(message: TgMessage) -> None:
    user = message.from_user
    async with get_sessionmaker()() as session:
        shops = await shops_of_user(session, user.id)
        if shops:
            shop = shops[0][0]
        else:
            shop = await create_shop(session, user.id, user.full_name, f"{user.full_name} do'koni")
            await session.commit()
    await message.answer(
        texts.ONBOARDING.format(shop=shop.name, bot=get_settings().bot_username, link=bot_link(shop.id)),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def on_help(message: TgMessage) -> None:
    await message.answer(texts.HELP)


async def _set_ai(message: TgMessage, enabled: bool) -> None:
    async with get_sessionmaker()() as session:
        shops = await shops_of_user(session, message.from_user.id)
        if not shops:
            await message.answer("Sizda do'kon yo'q. /start bosing.")
            return
        settings = await session.get(ShopSettings, shops[0][0].id)
        settings.ai_enabled = enabled
        await session.commit()
    await message.answer("🤖 AI yoqildi." if enabled else "⏸ AI to'xtatildi. Mijozlarga o'zingiz javob berasiz.")


@router.message(Command("ai_on"))
async def on_ai_on(message: TgMessage) -> None:
    await _set_ai(message, True)


@router.message(Command("ai_off"))
async def on_ai_off(message: TgMessage) -> None:
    await _set_ai(message, False)


@router.message(Command("status"))
async def on_status(message: TgMessage) -> None:
    async with get_sessionmaker()() as session:
        shops = await shops_of_user(session, message.from_user.id)
        if not shops:
            await message.answer("Sizda do'kon yo'q. /start bosing.")
            return
        shop = shops[0][0]
        settings = await session.get(ShopSettings, shop.id)
        usage = await current_usage(session, shop.id)
        ok, reason = await check_limits(session, shop)
        channels = (await session.scalars(select(Channel).where(Channel.shop_id == shop.id))).all()
    business = next((c for c in channels if c.type == "tg_business"), None)
    lines = [
        f"Do'kon: {shop.name}",
        f"Tarif: {shop.plan}",
        f"AI: {'yoqilgan' if settings.ai_enabled else 'to‘xtatilgan'}",
        f"Rejim: {MODE_NAMES.get(settings.ai_mode, settings.ai_mode)}",
        f"Lidlar: {'operatorlar guruhiga' if settings.lead_chat_id else 'sizga'}",
        f"Business: {'ulangan' if business and business.is_enabled else 'ulanmagan'}"
        + (" (javob ruxsati yo'q!)" if business and not business.can_reply else ""),
        f"Bu oy suhbatlar: {usage.conversations if usage else 0}",
        f"Holat: {'ishlayapti' if ok else reason}",
    ]
    await message.answer("\n".join(lines))


@router.message(Command("leads_here"))
async def on_leads_here(message: TgMessage) -> None:
    """Operatorlar guruhida yoziladi: shu guruh lidlar va operator xabarlari uchun belgilanadi."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Bu buyruqni operatorlar guruhida yozing (botni guruhga qo'shib).")
        return
    async with get_sessionmaker()() as session:
        shops = [(shop, su) for shop, su in await shops_of_user(session, message.from_user.id) if su.role == "owner"]
        if not shops:
            await message.answer("Faqat do'kon egasi guruhni belgilay oladi.")
            return
        settings = await session.get(ShopSettings, shops[0][0].id)
        settings.lead_chat_id = message.chat.id
        await session.commit()
    await message.answer(f"✅ Endi {shops[0][0].name} lidlari shu guruhga keladi.")


MODE_NAMES = {"sell": "sotuvchi (buyurtmagacha)", "lead": "lid yig'ish (telefon → operator)"}


@router.message(Command("mode"))
async def on_mode(message: TgMessage, command: CommandObject) -> None:
    mode = (command.args or "").strip().lower()
    async with get_sessionmaker()() as session:
        shops = await shops_of_user(session, message.from_user.id)
        if not shops:
            await message.answer("Sizda do'kon yo'q. /start bosing.")
            return
        settings = await session.get(ShopSettings, shops[0][0].id)
        if mode not in MODE_NAMES:
            await message.answer(
                f"Hozirgi rejim: {MODE_NAMES.get(settings.ai_mode, settings.ai_mode)}\n"
                "O'zgartirish: /mode sell yoki /mode lead"
            )
            return
        settings.ai_mode = mode
        await session.commit()
    await message.answer(f"✅ AI rejimi: {MODE_NAMES[mode]}")


@router.message(Command("tasks"))
async def on_tasks(message: TgMessage, command: CommandObject) -> None:
    """/tasks <matn> — AI uchun vazifalar/ssenariy. Argumentsiz — hozirgisini ko'rsatadi."""
    async with get_sessionmaker()() as session:
        shops = await shops_of_user(session, message.from_user.id)
        if not shops:
            await message.answer("Sizda do'kon yo'q. /start bosing.")
            return
        settings = await session.get(ShopSettings, shops[0][0].id)
        if not command.args:
            await message.answer(
                "Hozirgi vazifalar:\n" + (settings.ai_tasks or "(yo'q)") + "\n\nO'zgartirish: /tasks <matn>"
            )
            return
        settings.ai_tasks = command.args.strip()[:4000]
        await session.commit()
    await message.answer("✅ Vazifalar saqlandi. AI keyingi xabardan boshlab shunga amal qiladi.")


@router.message(F.chat.type == "private")
async def on_private_message(message: TgMessage) -> None:
    """Bot rejimi: mijoz do'kon havolasi orqali kirgan bo'lsa, xabari o'sha do'konga tegishli."""
    rt = get_runtime()
    async with get_sessionmaker()() as session:
        stmt = (
            select(Customer, Channel)
            .join(Channel, Channel.id == Customer.channel_id)
            .where(Channel.type == "tg_bot", Customer.external_user_id == message.from_user.id)
        )
        active_id = await rt.redis.get(active_shop_key(message.from_user.id))
        if active_id:
            stmt = stmt.where(Customer.id == int(active_id))
        row = (await session.execute(stmt.order_by(Customer.id.desc()).limit(1))).first()
        if row is None:
            if await shops_of_user(session, message.from_user.id):
                await message.answer(texts.HELP)
            else:
                await message.answer(texts.CUSTOMER_NO_SHOP)
            return
        conv = await ingest_customer_message(session, rt, row.Channel, message)
        await session.commit()
    if conv is not None:
        await enqueue_reply(rt, conv.id)


# ---------- Tugmalar ----------


async def _is_shop_member(session, shop_id: int, tg_user_id: int) -> bool:
    return bool(
        await session.scalar(
            select(ShopUser.id).where(ShopUser.shop_id == shop_id, ShopUser.telegram_user_id == tg_user_id)
        )
    )


async def _can_manage(session, shop_id: int, call: CallbackQuery) -> bool:
    """Do'kon xodimi yoki do'konning operatorlar guruhidagi a'zo."""
    if await _is_shop_member(session, shop_id, call.from_user.id):
        return True
    settings = await session.get(ShopSettings, shop_id)
    return bool(settings and settings.lead_chat_id and call.message and call.message.chat.id == settings.lead_chat_id)


ORDER_ACTIONS = {"c": "confirmed", "x": "cancelled", "s": "shipped"}
CUSTOMER_NOTICES = {
    "confirmed": texts.ORDER_CONFIRMED_CUSTOMER,
    "cancelled": texts.ORDER_CANCELLED_CUSTOMER,
    "shipped": texts.ORDER_SHIPPED_CUSTOMER,
}


async def notify_customer_about_order(bot: Bot, session, order: Order) -> None:
    customer = await session.get(Customer, order.customer_id)
    channel = await session.get(Channel, customer.channel_id)
    if channel.type == "test" or order.status not in CUSTOMER_NOTICES:
        return
    bcid = channel.business_connection_id if channel.type == "tg_business" else None
    try:
        await TelegramOutbound(bot, customer.chat_id, bcid).send_text(
            CUSTOMER_NOTICES[order.status].format(number=order.number)
        )
    except Exception:  # noqa: BLE001
        log.warning("Mijozga buyurtma holati yuborilmadi", exc_info=True)


@router.callback_query(F.data.startswith("ord:"))
async def on_order_action(call: CallbackQuery, bot: Bot) -> None:
    _, action, order_id = call.data.split(":")
    status = ORDER_ACTIONS.get(action)
    async with get_sessionmaker()() as session:
        order = await session.get(Order, int(order_id), with_for_update=True)
        if order is None or status is None or not await _is_shop_member(session, order.shop_id, call.from_user.id):
            await call.answer("Ruxsat yo'q", show_alert=True)
            return
        if order.status == status:
            await call.answer("Allaqachon bajarilgan")
            return
        await set_order_status(session, order, status)
        await session.commit()
        customer = await session.get(Customer, order.customer_id)
        await notify_customer_about_order(bot, session, order)
        try:
            await call.message.edit_text(
                order_text(order, customer) + f"\n\nHolat: <b>{status}</b>",
                parse_mode="HTML",
                reply_markup=order_keyboard(order, customer),
            )
        except Exception:  # noqa: BLE001
            log.debug("Xabar tahrirlanmadi", exc_info=True)
    await call.answer("Saqlandi")


@router.callback_query(F.data.startswith("conv:ai:"))
async def on_resume_ai(call: CallbackQuery) -> None:
    conv_id = int(call.data.split(":")[2])
    async with get_sessionmaker()() as session:
        conv = await session.get(Conversation, conv_id)
        if conv is None or not await _can_manage(session, conv.shop_id, call):
            await call.answer("Ruxsat yo'q", show_alert=True)
            return
        conv.status = "ai"
        conv.human_until = None
        if conv.stage == "handoff":
            conv.stage = "discovery"
        await session.commit()
    await call.answer("AI qayta yoqildi")


@router.callback_query(F.data.startswith("lead:c:"))
async def on_lead_contacted(call: CallbackQuery) -> None:
    lead_id = int(call.data.split(":")[2])
    async with get_sessionmaker()() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None or not await _can_manage(session, lead.shop_id, call):
            await call.answer("Ruxsat yo'q", show_alert=True)
            return
        lead.status = "contacted"
        await session.commit()
        who = call.from_user.full_name
    try:
        await call.message.edit_text((call.message.html_text or "") + f"\n\n✅ Bog'lanildi: {who}", parse_mode="HTML")
    except Exception:  # noqa: BLE001
        log.debug("Xabar tahrirlanmadi", exc_info=True)
    await call.answer("Saqlandi")
