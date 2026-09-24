"""AI suhbat oqimi: soxta LLM skripti bilan to'liq suhbat → buyurtma / lid."""

import json

import pytest
from sqlalchemy import select

from app.models import Lead, Message, Order, ProductVariant, ShopSettings
from app.services.conversation import VOICE_FAILED, reply_to_conversation
from app.telegram.outbound import RecordingOutbound
from tests.factories import make_business_channel, make_catalog, make_conversation, make_shop
from tests.fakes import DownLLM, RecordingNotifier, text_response, tool_response


@pytest.fixture
async def world(session, runtime):
    shop = await make_shop(session)
    products = await make_catalog(session, shop.id)
    channel = await make_business_channel(session, shop.id)
    customer, conv = await make_conversation(session, channel)
    await session.commit()
    return {"shop": shop, "channel": channel, "customer": customer, "conv": conv, **products}


async def say(session, conv, text: str, media: dict | None = None) -> None:
    session.add(Message(shop_id=conv.shop_id, conversation_id=conv.id, role="customer", content=text, media=media))
    await session.commit()


def last_tool_result(req: dict) -> dict:
    block = req["messages"][-1]["content"][0]
    assert block["type"] == "tool_result"
    return json.loads(block["content"])


async def reply(session, runtime, conv, notifier=None):
    outbound, notifier = RecordingOutbound(), notifier or RecordingNotifier()
    result = await reply_to_conversation(session, runtime, conv.id, outbound=outbound, notifier=notifier)
    return result, outbound, notifier


async def test_sell_flow_from_question_to_order(session, runtime, fake_llm, world):
    conv, dress = world["conv"], world["dress"]
    v42 = dress.variants[0]

    def after_search(req):
        found = last_tool_result(req)["products"]
        assert found[0]["variants"][0]["variant_id"] == v42.id
        return tool_response("send_product_photos", {"product_id": dress.id, "caption": "Qora ko'ylak"})

    fake_llm.steps = [
        tool_response("search_products", {"query": "qora ko'ylak", "size": "42"}),
        after_search,
        text_response("Ha, 42 razmer bor, narxi 250 000 so'm."),
    ]
    await say(session, conv, "Qora ko'ylak 42 razmer bormi? Raqamim 90 123 45 67")
    result, outbound, _ = await reply(session, runtime, conv)

    assert result.status == "replied"
    assert outbound.sent[0]["type"] == "photos" and len(outbound.sent[0]["photos"]) == 2
    assert outbound.sent[-1]["text"].startswith("Ha, 42 razmer bor")
    first_call = fake_llm.calls[0]
    assert "Dilnoza Style" in first_call["system"]
    assert "Qora ko'ylak — 250 000 so'm" in first_call["system"]  # kichik katalog promptda
    history = json.dumps(first_call["messages"], ensure_ascii=False)
    assert "[PHONE_1]" in history and "123 45 67" not in history
    assert "create_order" in {t["name"] for t in first_call["tools"]}

    # 2-xabar: savat → tasdiqsiz urinish → tasdiq bilan buyurtma
    fake_llm.steps = [
        tool_response("update_cart", {"action": "add", "variant_id": v42.id, "qty": 1}),
        tool_response(
            "create_order",
            {"name": "Aziza", "phone": "[PHONE_1]", "address": "Chilonzor 9", "customer_confirmed": False},
        ),
        lambda req: (
            last_tool_result(req)["error"]
            and tool_response(
                "create_order",
                # LLM noto'g'ri summa "aytsa" ham, server bazadan hisoblaydi
                {
                    "name": "Aziza",
                    "phone": "[PHONE_1]",
                    "address": "Chilonzor 9",
                    "customer_confirmed": True,
                    "total": 1,
                },
            )
        ),
        lambda req: text_response(f"Buyurtma #{last_tool_result(req)['order_number']} qabul qilindi"),
    ]
    await say(session, conv, "Olaman, Chilonzor 9, ismim Aziza. Ha, hammasi to'g'ri")
    result, outbound, notifier = await reply(session, runtime, conv)

    assert result.order_number == 1 and outbound.sent[-1]["text"] == "Buyurtma #1 qabul qilindi"
    order = await session.scalar(select(Order))
    assert order.total == 250_000 + 20_000 and order.phone == "+998901234567" and order.source == "ai"
    assert notifier.orders == [order] and notifier.flushed == 1
    await session.refresh(conv)
    assert conv.stage == "order_created" and conv.cart == []
    assert await session.scalar(select(ProductVariant.stock).where(ProductVariant.id == v42.id)) == 2
    ai_msgs = (await session.scalars(select(Message).where(Message.role == "ai"))).all()
    assert all(m.tokens_in > 0 and m.cost > 0 for m in ai_msgs)
    pending = await session.scalar(select(Message).where(Message.role == "customer", ~Message.answered))
    assert pending is None


async def test_lead_mode_collects_phone_and_hands_off(session, runtime, fake_llm, world):
    conv = world["conv"]
    settings = await session.get(ShopSettings, world["shop"].id)
    settings.ai_mode = "lead"
    settings.ai_tasks = "Avval do'konni tanishtir, keyin telefon raqamini so'ra."
    await session.commit()

    def check_prompt(req):
        names = {t["name"] for t in req["tools"]}
        assert "save_lead" in names and "create_order" not in names and "update_cart" not in names
        assert "Avval do'konni tanishtir" in req["system"] and "telefon raqamingizni" in req["system"]
        return text_response("Assalomu alaykum! To'liq ma'lumot uchun telefon raqamingizni qoldira olasizmi?")

    fake_llm.steps = [check_prompt]
    await say(session, conv, "Salom, ko'ylaklar bormi?")
    result, outbound, _ = await reply(session, runtime, conv)
    assert "telefon raqamingizni" in outbound.sent[-1]["text"]

    fake_llm.steps = [
        tool_response("create_order", {"name": "A", "phone": "[PHONE_1]", "address": "x", "customer_confirmed": True}),
        lambda req: (
            "error" in last_tool_result(req)
            and tool_response("save_lead", {"phone": "[PHONE_1]", "name": "Aziza", "interest": "qora ko'ylak"})
        ),
        text_response("Rahmat! Operator tez orada qo'ng'iroq qiladi."),
    ]
    await say(session, conv, "Mayli, +998 91 765 43 21")
    result, outbound, notifier = await reply(session, runtime, conv)

    lead = await session.scalar(select(Lead))
    assert lead.phone == "+998917654321" and lead.interest == "qora ko'ylak" and lead.channel_type == "tg_business"
    assert result.lead_id == lead.id and notifier.leads == [lead]
    assert await session.scalar(select(Order.id)) is None
    await session.refresh(conv)
    assert conv.status == "human" and conv.stage == "lead_captured"

    # Operatorga o'tgan: keyingi xabarga AI javob bermaydi
    await say(session, conv, "Qachon qo'ng'iroq qilasiz?")
    result, outbound, _ = await reply(session, runtime, conv)
    assert result.status == "ai_off" and outbound.sent == []


async def test_lead_without_handoff_keeps_ai_active(session, runtime, fake_llm, world):
    conv = world["conv"]
    settings = await session.get(ShopSettings, world["shop"].id)
    settings.handoff_after_lead = False
    await session.commit()
    fake_llm.steps = [
        tool_response("save_lead", {"phone": "901234567", "interest": "sumka"}),
        tool_response("save_lead", {"phone": "901234567", "interest": "charm sumka"}),
        text_response("Raqamingiz yozib olindi."),
    ]
    await say(session, conv, "901234567")
    await reply(session, runtime, conv)
    leads = (await session.scalars(select(Lead))).all()
    assert len(leads) == 1 and leads[0].interest == "charm sumka"  # takror lid yaratilmaydi
    await session.refresh(conv)
    assert conv.status == "ai"


async def test_keyword_handoff_skips_llm(session, runtime, fake_llm, world):
    await say(session, world["conv"], "Operator bilan gaplashmoqchiman")
    result, outbound, notifier = await reply(session, runtime, world["conv"])
    assert result.status == "handoff" and fake_llm.calls == []
    assert "menejerga" in outbound.sent[-1]["text"] and notifier.handoffs
    event = await session.scalar(select(Message).where(Message.role == "system"))
    assert event.content.startswith("handoff:")


async def test_llm_down_sends_fallback(session, runtime, world):
    runtime.llm = DownLLM()
    await say(session, world["conv"], "Salom")
    result, outbound, _ = await reply(session, runtime, world["conv"])
    assert result.status == "llm_failed"
    assert outbound.sent[-1]["text"] == "Xabaringiz qabul qilindi, tez orada javob beramiz."


async def test_invalid_tool_input_is_reported_to_llm(session, runtime, fake_llm, world):
    fake_llm.steps = [
        tool_response("update_cart", {"action": "explode"}),
        lambda req: text_response("xato" if "error" in last_tool_result(req) else "?"),
    ]
    await say(session, world["conv"], "savatga qo'sh")
    _, outbound, _ = await reply(session, runtime, world["conv"])
    assert outbound.sent[-1]["text"] == "xato"


async def test_voice_without_stt_asks_for_text(session, runtime, fake_llm, world):
    runtime.bot = None  # yuklab bo'lmaydi
    await say(session, world["conv"], "", media={"type": "voice", "file_id": "v1"})
    await reply(session, runtime, world["conv"])
    msg = await session.scalar(select(Message).where(Message.role == "customer"))
    assert msg.content == VOICE_FAILED
    assert "matn bilan yozishini" in json.dumps(fake_llm.calls[0]["messages"], ensure_ascii=False)


async def test_trial_expired_blocks_reply(session, runtime, fake_llm, world):
    from datetime import UTC, datetime, timedelta

    world["shop"].trial_ends_at = datetime.now(UTC) - timedelta(days=1)
    await session.commit()
    await say(session, world["conv"], "Salom")
    result, outbound, _ = await reply(session, runtime, world["conv"])
    assert result.status == "blocked:trial_expired" and outbound.sent == [] and fake_llm.calls == []


async def test_llm_rejected_request_sends_fallback(session, runtime, world):
    from app.ai.llm.base import LLMError

    class RejectingLLM:
        async def chat(self, **kwargs):
            raise LLMError("401 invalid api key")

    runtime.llm = RejectingLLM()
    await say(session, world["conv"], "Salom")
    result, outbound, _ = await reply(session, runtime, world["conv"])
    assert result.status == "llm_failed"
    assert outbound.sent[-1]["text"] == "Xabaringiz qabul qilindi, tez orada javob beramiz."
