"""Webhook → handler → DB → worker → Telegram javobi (FakeBot orqali)."""

import time

import pytest
from aiogram.methods import AnswerCallbackQuery
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import create_app
from app.models import Channel, Conversation, Message, Order, Shop, ShopSettings
from app.services import cart as cart_svc
from app.services.ingest import debounce_key
from app.services.orders import create_order
from app.telegram.bot import build_dispatcher
from app.worker.tasks import process_conversation
from tests.factories import CUSTOMER_ID, OWNER_ID

SECRET = "hook-secret"
_update_ids = iter(range(1, 10_000))


@pytest.fixture
async def client(runtime):
    app = create_app()
    app.state.dispatcher = build_dispatcher()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def user(uid: int, name: str = "User") -> dict:
    return {"id": uid, "is_bot": False, "first_name": name}


async def post_update(client, payload: dict, update_id: int | None = None):
    body = {"update_id": update_id or next(_update_ids), **payload}
    return await client.post(f"/tg/webhook/{SECRET}", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})


def business_message(text: str, from_id: int = CUSTOMER_ID, msg_id: int = 10) -> dict:
    return {
        "business_message": {
            "message_id": msg_id,
            "date": int(time.time()),
            "chat": {"id": CUSTOMER_ID, "type": "private", "first_name": "Aziza"},
            "from": user(from_id, "Aziza" if from_id == CUSTOMER_ID else "Dilnoza"),
            "business_connection_id": "bc-1",
            "text": text,
        }
    }


async def connect_business(client, can_reply: bool = True):
    return await post_update(
        client,
        {
            "business_connection": {
                "id": "bc-1",
                "user": user(OWNER_ID, "Dilnoza"),
                "user_chat_id": OWNER_ID,
                "date": int(time.time()),
                "rights": {"can_reply": can_reply},
                "is_enabled": True,
            }
        },
    )


async def test_webhook_rejects_bad_secret(client):
    resp = await client.post("/tg/webhook/wrong", json={"update_id": 1})
    assert resp.status_code == 403


async def test_business_connection_creates_shop_and_channel(client, session, fake_bot):
    assert (await connect_business(client)).status_code == 200
    channel = await session.scalar(select(Channel))
    assert channel.business_connection_id == "bc-1" and channel.can_reply and channel.owner_user_id == OWNER_ID
    shop = await session.get(Shop, channel.shop_id)
    assert shop.plan == "trial" and shop.trial_ends_at is not None
    assert "Business ulandi" in fake_bot.sent()[-1].text


async def test_business_connection_without_reply_right_warns(client, session, fake_bot):
    await connect_business(client, can_reply=False)
    assert "ruxsati yo'q" in fake_bot.sent()[-1].text


async def test_customer_message_flow_with_debounce_and_dedup(client, session, runtime, fake_bot, fake_llm):
    await connect_business(client)
    fake_llm.steps = [lambda req: fake_llm_answer(req)]

    resp = await post_update(client, business_message("Salom", msg_id=10), update_id=5000)
    assert resp.json() == {"ok": True}
    assert (await post_update(client, business_message("Salom", msg_id=10), update_id=5000)).json()["duplicate"]
    await post_update(client, business_message("Ko'ylak bormi?", msg_id=11))

    conv = await session.scalar(select(Conversation))
    msgs = (await session.scalars(select(Message).where(Message.role == "customer"))).all()
    assert [m.content for m in msgs] == ["Salom", "Ko'ylak bormi?"]
    token = await runtime.redis.get(debounce_key(conv.id))

    assert await process_conversation({}, conv.id, "old-token") == "superseded"
    assert await process_conversation({}, conv.id, token) == "replied"

    reply = [m for m in fake_bot.sent() if m.chat_id == CUSTOMER_ID][-1]
    assert reply.business_connection_id == "bc-1" and reply.text == "Ikkala xabar birga keldi"
    assert len(fake_llm.calls) == 1  # 2 xabarga bitta javob


def fake_llm_answer(req):
    from tests.fakes import text_response

    last = req["messages"][-1]["content"][0]["text"]
    assert "Salom" in last and "Ko'ylak bormi?" in last
    return text_response("Ikkala xabar birga keldi")


async def test_own_bot_messages_are_ignored(client, session):
    await connect_business(client)
    payload = business_message("AI javobi", from_id=OWNER_ID)
    payload["business_message"]["sender_business_bot"] = {"id": 1, "is_bot": True, "first_name": "bot"}
    await post_update(client, payload)
    assert await session.scalar(select(Message)) is None


async def test_staff_message_silences_ai(client, session, runtime, fake_bot, fake_llm):
    await connect_business(client)
    await post_update(client, business_message("Narxi qancha?", msg_id=20))
    await post_update(client, business_message("Hozir aytaman", from_id=OWNER_ID, msg_id=21))
    conv = await session.scalar(select(Conversation))
    assert conv.status == "human" and conv.human_until is not None

    await post_update(client, business_message("Kutyapman", msg_id=22))
    token = await runtime.redis.get(debounce_key(conv.id))
    assert await process_conversation({}, conv.id, token) == "ai_off"
    assert fake_llm.calls == []
    roles = [m.role for m in (await session.scalars(select(Message).order_by(Message.id))).all()]
    assert roles == ["customer", "staff", "customer"]


async def test_seller_start_creates_shop(client, session, fake_bot):
    await post_update(
        client,
        {
            "message": {
                "message_id": 1,
                "date": int(time.time()),
                "chat": {"id": OWNER_ID, "type": "private", "first_name": "Dilnoza"},
                "from": user(OWNER_ID, "Dilnoza"),
                "text": "/start",
                "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
            }
        },
    )
    shop = await session.scalar(select(Shop))
    assert shop is not None
    assert "Telegram Business" in fake_bot.sent()[-1].text and f"shop_{shop.id}" in fake_bot.sent()[-1].text


def command(text: str, chat: dict, from_id: int = OWNER_ID) -> dict:
    cmd = text.split()[0]
    return {
        "message": {
            "message_id": 2,
            "date": int(time.time()),
            "chat": chat,
            "from": user(from_id),
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(cmd)}],
        }
    }


async def test_seller_commands_mode_tasks_and_lead_group(client, session, fake_bot):
    private = {"id": OWNER_ID, "type": "private", "first_name": "D"}
    await post_update(client, command("/start", private))
    await post_update(client, command("/mode lead", private))
    await post_update(client, command("/tasks Avval tanishtir, keyin raqam so'ra", private))
    await post_update(client, command("/leads_here", {"id": -100500, "type": "supergroup", "title": "Operatorlar"}))
    settings = await session.scalar(select(ShopSettings))
    assert settings.ai_mode == "lead"
    assert settings.ai_tasks == "Avval tanishtir, keyin raqam so'ra"
    assert settings.lead_chat_id == -100500
    # Begona odam guruhni o'zgartira olmaydi
    await post_update(client, command("/leads_here", {"id": -1, "type": "group", "title": "x"}, from_id=999))
    await session.refresh(settings)
    assert settings.lead_chat_id == -100500


async def test_bot_mode_customer_via_deep_link(client, session, runtime, fake_bot, fake_llm):
    await post_update(client, command("/start", {"id": OWNER_ID, "type": "private", "first_name": "D"}))
    shop = await session.scalar(select(Shop))
    chat = {"id": 4242, "type": "private", "first_name": "Mijoz"}
    await post_update(client, command(f"/start shop_{shop.id}", chat, from_id=4242))
    assert "xush kelibsiz" in fake_bot.sent()[-1].text
    await post_update(
        client,
        {"message": {"message_id": 3, "date": int(time.time()), "chat": chat, "from": user(4242), "text": "Salom"}},
    )
    conv = await session.scalar(select(Conversation))
    token = await runtime.redis.get(debounce_key(conv.id))
    assert await process_conversation({}, conv.id, token) == "replied"
    reply = fake_bot.sent()[-1]
    assert reply.chat_id == 4242 and reply.business_connection_id is None


async def test_order_confirm_button_notifies_customer(client, session, fake_bot):
    await connect_business(client)
    from tests.factories import make_catalog

    channel = await session.scalar(select(Channel))
    await post_update(client, business_message("Salom"))
    conv = await session.scalar(select(Conversation))
    products = await make_catalog(session, channel.shop_id)
    await cart_svc.update_cart(session, conv, "add", products["bag"].variants[0].id, 1)
    from app.models import Customer

    customer = await session.get(Customer, conv.customer_id)
    settings = await session.get(ShopSettings, channel.shop_id)
    order = await create_order(
        session, conv=conv, customer=customer, settings=settings, name="A", phone="+998901234567", address="Toshkent"
    )
    await session.commit()

    callback = {
        "callback_query": {
            "id": "cb1",
            "from": user(OWNER_ID),
            "chat_instance": "ci",
            "data": f"ord:c:{order.id}",
            "message": {
                "message_id": 99,
                "date": int(time.time()),
                "chat": {"id": OWNER_ID, "type": "private", "first_name": "D"},
                "text": "Yangi buyurtma",
            },
        }
    }
    await post_update(client, callback)
    await session.refresh(order)
    assert order.status == "confirmed"
    to_customer = [m for m in fake_bot.sent() if m.chat_id == CUSTOMER_ID]
    assert "tasdiqlandi" in to_customer[-1].text and to_customer[-1].business_connection_id == "bc-1"

    # Begona foydalanuvchi tugmani bosa olmaydi
    callback["callback_query"]["from"] = user(999)
    callback["callback_query"]["data"] = f"ord:x:{order.id}"
    await post_update(client, callback)
    await session.refresh(order)
    assert order.status == "confirmed"
    assert any(isinstance(c, AnswerCallbackQuery) and c.show_alert for c in fake_bot.calls)
    assert await session.scalar(select(Order.id)) == order.id
