"""Mijoz rasmi: AI'ga image bloki sifatida uzatiladi (rasm bo'yicha qidiruv)."""

import base64

import pytest

from app.models import Message
from app.services import conversation as conv_svc
from app.services.conversation import reply_to_conversation
from app.telegram.outbound import RecordingOutbound
from tests.factories import make_business_channel, make_catalog, make_conversation, make_shop
from tests.fakes import RecordingNotifier, text_response, tool_response

JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png"


@pytest.fixture
async def world(session, runtime):
    shop = await make_shop(session)
    products = await make_catalog(session, shop.id)
    channel = await make_business_channel(session, shop.id)
    customer, conv = await make_conversation(session, channel)
    await session.commit()
    return {"shop": shop, "conv": conv, **products}


def downloads(mapping: dict):
    async def fake(rt, media):
        value = mapping[media.get("file_id") or media.get("url")]
        if isinstance(value, Exception):
            raise value
        return value

    return fake


async def send_photo(session, conv, key: str, caption: str = "", field: str = "file_id"):
    session.add(
        Message(
            shop_id=conv.shop_id,
            conversation_id=conv.id,
            role="customer",
            content=f"[Rasm yubordi] {caption}".strip(),
            media={"type": "photo", field: key},
        )
    )
    await session.commit()


async def reply(session, runtime, conv):
    return await reply_to_conversation(
        session, runtime, conv.id, outbound=RecordingOutbound(), notifier=RecordingNotifier()
    )


async def test_photo_is_passed_to_llm_and_drives_search(session, runtime, fake_llm, world, monkeypatch):
    monkeypatch.setattr(conv_svc, "_download_media", downloads({"tg-photo-1": JPEG}))
    seen = {}

    def look(req):
        content = req["messages"][-1]["content"]
        seen["first"] = content[0]
        seen["texts"] = [b["text"] for b in content if b["type"] == "text"]
        assert "Mijoz rasm yuborsa" in req["system"]
        return tool_response("search_products", {"query": "qora ko'ylak"})

    fake_llm.steps = [look, text_response("Ha, shunga o'xshash qora ko'ylak bor — 250 000 so'm.")]
    await send_photo(session, world["conv"], "tg-photo-1", "shu bormi?")
    result = await reply(session, runtime, world["conv"])

    assert seen["first"] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(JPEG).decode()},
    }
    assert any("shu bormi?" in t for t in seen["texts"])
    assert result.tools[0]["result"]["products"][0]["name"] == "Qora ko'ylak"
    # Keyingi so'rov (tool natijasidan keyin) rasmni takror yubormaydi
    assert fake_llm.calls[1]["messages"][-1]["content"][0]["type"] == "tool_result"


async def test_instagram_url_photo_png(session, runtime, fake_llm, world, monkeypatch):
    monkeypatch.setattr(conv_svc, "_download_media", downloads({"https://cdn.ig/p.png": PNG}))
    fake_llm.steps = [
        lambda req: req["messages"][-1]["content"][0]["source"]["media_type"] == "image/png" and text_response("ok")
    ]
    await send_photo(session, world["conv"], "https://cdn.ig/p.png", field="url")
    assert (await reply(session, runtime, world["conv"])).text == "ok"


async def test_bad_or_failed_images_are_skipped(session, runtime, fake_llm, world, monkeypatch):
    monkeypatch.setattr(
        conv_svc,
        "_download_media",
        downloads({"not-image": b"hello", "boom": RuntimeError("network"), "ok": JPEG}),
    )
    for key in ("not-image", "boom", "ok"):
        await send_photo(session, world["conv"], key)
    await reply(session, runtime, world["conv"])
    images = [b for b in fake_llm.calls[0]["messages"][-1]["content"] if b["type"] == "image"]
    assert len(images) == 1


async def test_at_most_three_images(session, runtime, fake_llm, world, monkeypatch):
    monkeypatch.setattr(conv_svc, "_download_media", downloads({f"p{i}": JPEG for i in range(5)}))
    for i in range(5):
        await send_photo(session, world["conv"], f"p{i}")
    await reply(session, runtime, world["conv"])
    images = [b for b in fake_llm.calls[0]["messages"][-1]["content"] if b["type"] == "image"]
    assert len(images) == 3


async def test_text_message_has_no_image(session, runtime, fake_llm, world):
    session.add(
        Message(shop_id=world["conv"].shop_id, conversation_id=world["conv"].id, role="customer", content="Salom")
    )
    await session.commit()
    await reply(session, runtime, world["conv"])
    assert all(b["type"] == "text" for b in fake_llm.calls[0]["messages"][-1]["content"])
