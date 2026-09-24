from datetime import UTC, datetime, timedelta

import pytest
from aiogram.methods import SendMessage
from sqlalchemy import select

from app.models import Message, ProductVariant, Shop, ShopSettings
from app.services.reminders import due_conversations, reminder_text, send_cart_reminder
from app.worker.tasks import send_cart_reminders
from tests.factories import CUSTOMER_ID, make_business_channel, make_catalog, make_conversation, make_shop


@pytest.fixture
async def world(session, runtime):
    shop = await make_shop(session)
    catalog = await make_catalog(session, shop.id)
    channel = await make_business_channel(session, shop.id)
    customer, conv = await make_conversation(session, channel)
    variants = {
        (v.product_id, (v.attrs or {}).get("size")): v.id
        for v in await session.scalars(select(ProductVariant).where(ProductVariant.shop_id == shop.id))
    }
    dress42 = variants[(catalog["dress"].id, "42")]
    dress44 = variants[(catalog["dress"].id, "44")]  # omborda yo'q
    bag = variants[(catalog["bag"].id, None)]
    conv.cart = [{"variant_id": dress42, "qty": 1}, {"variant_id": bag, "qty": 2}]
    conv.last_message_at = datetime.now(UTC) - timedelta(hours=4)
    session.add(Message(shop_id=shop.id, conversation_id=conv.id, role="customer", content="Salom, ko'ylak bormi?"))
    await session.commit()
    return {"shop": shop, "channel": channel, "conv": conv, "dress44": dress44}


def sent_texts(bot) -> list[SendMessage]:
    return bot.sent(SendMessage)


async def test_reminder_is_sent_once_with_db_prices(session, runtime, fake_bot, world):
    conv = world["conv"]
    assert await due_conversations(session) == [conv.id]
    assert (await send_cart_reminder(session, runtime, conv.id)).status == "sent"

    [msg] = sent_texts(fake_bot)
    assert msg.chat_id == CUSTOMER_ID and msg.business_connection_id == "bc-1"
    assert msg.text.startswith("Assalomu alaykum, Aziza!")
    assert "• Qora ko'ylak (42, qora) × 1 — 250 000 so'm" in msg.text
    assert "• Charm sumka (jigarrang) × 2 — 360 000 so'm" in msg.text
    assert "Jami: 610 000 so'm" in msg.text and "rasmiylashtirib" in msg.text
    saved = await session.scalar(select(Message).where(Message.role == "ai"))
    assert saved.media == {"type": "cart_reminder"} and saved.content == msg.text

    # Ikkinchi marta — yo'q
    assert await due_conversations(session) == []
    assert (await send_cart_reminder(session, runtime, conv.id)).status == "already"
    assert len(sent_texts(fake_bot)) == 1

    # Mijoz yana yozib, yana jim qolsa — yangi eslatma mumkin
    await session.refresh(conv)
    conv.cart_reminded_at = datetime.now(UTC) - timedelta(hours=5)
    await session.commit()
    assert await due_conversations(session) == [conv.id]


@pytest.mark.parametrize(
    "change",
    [
        "recent",
        "too_old",
        "empty_cart",
        "human",
        "disabled",
        "longer_delay",
        "ai_off",
        "channel_off",
    ],
)
async def test_not_due(session, runtime, world, change):
    conv = world["conv"]
    settings = await session.get(ShopSettings, world["shop"].id)
    now = datetime.now(UTC)
    if change == "recent":
        conv.last_message_at = now - timedelta(hours=1)
    elif change == "too_old":
        conv.last_message_at = now - timedelta(hours=23)
    elif change == "empty_cart":
        conv.cart = []  # buyurtma berilgach savat bo'shatiladi
    elif change == "human":
        conv.status = "human"
    elif change == "disabled":
        settings.cart_reminder_enabled = False
    elif change == "longer_delay":
        settings.cart_reminder_hours = 6
    elif change == "ai_off":
        settings.ai_enabled = False
    elif change == "channel_off":
        world["channel"].is_enabled = False
    await session.commit()
    assert await due_conversations(session) == []


async def test_russian_and_out_of_stock(session, runtime, fake_bot, world):
    conv = world["conv"]
    session.add(
        Message(shop_id=conv.shop_id, conversation_id=conv.id, role="customer", content="Здравствуйте, есть платье?")
    )
    conv.cart = [*conv.cart, {"variant_id": world["dress44"], "qty": 1}]
    await session.commit()
    assert (await send_cart_reminder(session, runtime, conv.id)).status == "sent"
    [msg] = sent_texts(fake_bot)
    assert msg.text.startswith("Здравствуйте, Aziza!") and "Итого: 610 000 сум" in msg.text
    assert "(44" not in msg.text  # omborda yo'q variant eslatilmaydi


async def test_only_out_of_stock_items_are_skipped(session, runtime, fake_bot, world):
    conv = world["conv"]
    conv.cart = [{"variant_id": world["dress44"], "qty": 1}]
    await session.commit()
    assert (await send_cart_reminder(session, runtime, conv.id)).status == "empty"
    assert sent_texts(fake_bot) == []
    assert await due_conversations(session) == []


async def test_expired_trial_blocks_reminder(session, runtime, fake_bot, world):
    shop = await session.get(Shop, world["shop"].id)
    shop.trial_ends_at = datetime.now(UTC) - timedelta(days=1)
    await session.commit()
    assert (await send_cart_reminder(session, runtime, world["conv"].id)).status == "blocked"
    assert sent_texts(fake_bot) == []


async def test_worker_task_respects_conversation_lock(session, runtime, fake_bot, world, redis):
    conv_id = world["conv"].id
    lock = redis.lock(f"lock:conv:{conv_id}", timeout=30)
    await lock.acquire()
    assert await send_cart_reminders({}) == "due=1 sent=0"
    await lock.release()
    assert await send_cart_reminders({}) == "due=1 sent=1"
    assert await send_cart_reminders({}) == "due=0 sent=0"
    assert len(sent_texts(fake_bot)) == 1


def test_reminder_text_uz_cyrillic():
    cart = {"items": [{"name": "Кўйлак", "attrs": {}, "qty": 1, "line_total": 100_000}], "subtotal": 100_000}
    text = reminder_text(cart, "uz_cyrl", None)
    assert text.startswith("Ассалому алайкум!") and "Жами: 100 000 сўм" in text
