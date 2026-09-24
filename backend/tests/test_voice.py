"""Ovozli javoblar: Azure TTS so'rovi, rejimlar, kanal bo'yicha yuborish, test chat."""

import base64
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from aiogram.methods import SendMessage, SendVoice
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import create_app
from app.models import Channel, Message, ShopSettings
from app.services import tts as tts_svc
from app.services.conversation import reply_to_conversation
from app.services.crypto import encrypt
from app.services.tts import AzureTTS, should_speak, uz_cyr_to_lat, voice_for
from tests.factories import make_business_channel, make_conversation, make_shop
from tests.fakes import FakeTTS, text_response


def test_helpers():
    assert uz_cyr_to_lat("Қора кўйлак, ғишт, ер") == "Qora koʻylak, gʻisht, yer"
    assert voice_for("Здравствуйте, есть в наличии", "female")[:2] == ("ru-RU", "ru-RU-SvetlanaNeural")
    assert voice_for("Salom, bor!", "male")[:2] == ("uz-UZ", "uz-UZ-SardorNeural")
    assert voice_for("Салом, бор!", "female") == ("uz-UZ", "uz-UZ-MadinaNeural", "Salom, bor!")
    assert should_speak("always", False) and should_speak("on_voice", True)
    assert not should_speak("on_voice", False) and not should_speak("off", True)


async def test_azure_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = request.content.decode()
        return httpx.Response(200, content=b"OggS-audio", headers={"content-type": "audio/ogg"})

    tts_svc._transport = httpx.MockTransport(handler)
    try:
        audio = await AzureTTS("az-key", "westeurope").synthesize("Salom 😊 narxi **250 000** so'm & bor", "female")
    finally:
        tts_svc._transport = None
    assert audio == b"OggS-audio"
    assert seen["url"] == "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1"
    assert seen["headers"]["ocp-apim-subscription-key"] == "az-key"
    assert seen["headers"]["x-microsoft-outputformat"] == "ogg-24khz-16bit-mono-opus"
    assert seen["headers"]["content-type"] == "application/ssml+xml"
    assert "xml:lang='uz-UZ'" in seen["body"] and "uz-UZ-MadinaNeural" in seen["body"]
    assert "narxi 250 000 so'm &amp; bor" in seen["body"] and "😊" not in seen["body"]


async def test_azure_error_returns_none():
    tts_svc._transport = httpx.MockTransport(lambda r: httpx.Response(401, text="bad key"))
    try:
        assert await AzureTTS("x", "eastus").synthesize("Salom") is None
    finally:
        tts_svc._transport = None


@pytest.fixture
async def tg_world(session, runtime):
    shop = await make_shop(session)
    channel = await make_business_channel(session, shop.id)
    customer, conv = await make_conversation(session, channel)
    await session.commit()
    return {"shop": shop, "channel": channel, "conv": conv, "customer": customer}


async def set_voice(session, shop_id, mode, gender="female"):
    settings = await session.get(ShopSettings, shop_id)
    settings.voice_mode, settings.voice_gender = mode, gender
    await session.commit()


async def say(session, conv, text, voice=False):
    media = {"type": "voice", "transcribed": True} if voice else None
    session.add(Message(shop_id=conv.shop_id, conversation_id=conv.id, role="customer", content=text, media=media))
    await session.commit()


async def test_always_mode_sends_voice_then_text(session, runtime, fake_bot, fake_llm, tg_world):
    runtime.tts = FakeTTS()
    await set_voice(session, tg_world["shop"].id, "always", "male")
    fake_llm.steps = [text_response("Ha, bor. Narxi 250 000 so'm.")]
    await say(session, tg_world["conv"], "Qora ko'ylak bormi?")
    result = await reply_to_conversation(session, runtime, tg_world["conv"].id)

    assert result.voice and runtime.tts.calls == [("Ha, bor. Narxi 250 000 so'm.", "male")]
    sent = [c for c in fake_bot.calls if isinstance(c, SendVoice | SendMessage)]
    assert isinstance(sent[0], SendVoice) and isinstance(sent[1], SendMessage)
    assert sent[0].business_connection_id == "bc-1" and sent[0].chat_id == tg_world["customer"].chat_id
    ai = await session.scalar(select(Message).where(Message.role == "ai"))
    assert ai.media == {"type": "voice_reply"}


async def test_on_voice_mode_only_answers_voice_with_voice(session, runtime, fake_bot, fake_llm, tg_world):
    runtime.tts = FakeTTS()
    await set_voice(session, tg_world["shop"].id, "on_voice")
    await say(session, tg_world["conv"], "Salom")
    result = await reply_to_conversation(session, runtime, tg_world["conv"].id)
    assert not result.voice and runtime.tts.calls == []

    await say(session, tg_world["conv"], "Qora ko'ylak bormi", voice=True)
    result = await reply_to_conversation(session, runtime, tg_world["conv"].id)
    assert result.voice and fake_bot.sent(SendVoice)


async def test_off_mode_and_missing_tts(session, runtime, fake_bot, fake_llm, tg_world):
    await set_voice(session, tg_world["shop"].id, "always")
    await say(session, tg_world["conv"], "Salom")
    assert not (await reply_to_conversation(session, runtime, tg_world["conv"].id)).voice  # TTS sozlanmagan
    runtime.tts = FakeTTS()
    await set_voice(session, tg_world["shop"].id, "off")
    await say(session, tg_world["conv"], "Salom", voice=True)
    assert not (await reply_to_conversation(session, runtime, tg_world["conv"].id)).voice
    assert not fake_bot.sent(SendVoice)


async def test_tts_failure_still_sends_text(session, runtime, fake_bot, fake_llm, tg_world):
    runtime.tts = FakeTTS(fail=True)
    await set_voice(session, tg_world["shop"].id, "always")
    fake_llm.steps = [text_response("Javob matni")]
    await say(session, tg_world["conv"], "Salom")
    result = await reply_to_conversation(session, runtime, tg_world["conv"].id)
    assert not result.voice and fake_bot.sent(SendMessage)[-1].text == "Javob matni"


async def test_long_reply_is_text_only(session, runtime, fake_bot, fake_llm, tg_world):
    runtime.tts = FakeTTS()
    await set_voice(session, tg_world["shop"].id, "always")
    fake_llm.steps = [text_response("uzun " * 400)]
    await say(session, tg_world["conv"], "Salom")
    assert not (await reply_to_conversation(session, runtime, tg_world["conv"].id)).voice
    assert runtime.tts.calls == []


async def test_instagram_gets_text_only(session, runtime, fake_llm):
    from app.instagram import client as ig

    sent = []
    ig._transport = httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(200, json={"message_id": "m"}))[1])
    try:
        runtime.tts = FakeTTS()
        shop = await make_shop(session)
        channel = Channel(
            shop_id=shop.id,
            type="instagram",
            external_id="1784",
            token_encrypted=encrypt("t"),
            token_expires_at=datetime.now(UTC) + timedelta(days=30),
            can_reply=True,
            is_enabled=True,
        )
        session.add(channel)
        await session.flush()
        _, conv = await make_conversation(session, channel)
        await session.commit()
        await set_voice(session, shop.id, "always")
        await say(session, conv, "Salom")
        result = await reply_to_conversation(session, runtime, conv.id)
    finally:
        ig._transport = None
    assert not result.voice and runtime.tts.calls == []
    assert any(b'"text"' in r.content for r in sent)


async def test_test_chat_returns_playable_voice(session, runtime, fake_llm):
    runtime.tts = FakeTTS(audio=b"OggS-demo")
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        await client.post(
            "/api/auth/register",
            json={"name": "D", "phone": "90 123 45 67", "password": "juda-maxfiy-1", "shop_name": "S"},
        )
        settings = (await client.get("/api/settings")).json()
        assert settings["voice_available"] is True and settings["voice_mode"] == "off"
        settings.update(voice_mode="on_voice", voice_gender="male")
        saved = (await client.put("/api/settings", json=settings)).json()
        assert saved["voice_mode"] == "on_voice" and saved["voice_gender"] == "male"

        fake_llm.steps = [text_response("Salom! Qanday yordam beray?")]
        resp = (await client.post("/api/test-chat", json={"message": "Salom", "as_voice": True})).json()
    assert resp["voice"] is True
    voice = next(r for r in resp["replies"] if r["type"] == "voice")
    assert base64.b64decode(voice["audio_b64"]) == b"OggS-demo" and voice["mime"] == "audio/ogg"
    assert resp["replies"][-1]["text"] == "Salom! Qanday yordam beray?"
