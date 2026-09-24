"""Instagram Direct: webhook, javob yuborish, echo, OAuth ulash, token yangilash (Graph API soxta transport bilan)."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.instagram import client as ig
from app.main import create_app
from app.models import Channel, Conversation, Customer, Message, Order, ShopSettings
from app.services import cart as cart_svc
from app.services.crypto import decrypt, encrypt
from app.services.ingest import debounce_key
from app.services.orders import create_order
from app.worker.tasks import process_conversation, refresh_instagram_tokens
from tests.factories import make_catalog, make_shop
from tests.fakes import text_response, tool_response

IG_ID = "17841400000000001"
IGSID = 7_100_000_000_000_001


class FakeGraph:
    """graph.instagram.com va api.instagram.com o'rniga."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.counter = 0

    def sent_messages(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.method == "POST" and r.url.path.endswith("/messages")]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, host = request.url.path, request.url.host
        if host == "api.instagram.com" and path == "/oauth/access_token":
            return httpx.Response(200, json={"access_token": "short-token", "user_id": 123})
        if path == "/access_token":
            return httpx.Response(
                200, json={"access_token": "long-token", "token_type": "bearer", "expires_in": 5184000}
            )
        if path == "/refresh_access_token":
            return httpx.Response(200, json={"access_token": "long-token-2", "expires_in": 5184000})
        if path.endswith("/me/subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        if path.endswith("/me"):
            return httpx.Response(200, json={"user_id": IG_ID, "username": "dilnoza_style", "id": "app-scoped"})
        if path.endswith("/messages"):
            body = json.loads(request.content)
            if "sender_action" in body:
                return httpx.Response(200, json={"recipient_id": body["recipient"]["id"]})
            self.counter += 1
            return httpx.Response(
                200, json={"recipient_id": body["recipient"]["id"], "message_id": f"mid.out.{self.counter}"}
            )
        if path.endswith(f"/{IGSID}"):
            return httpx.Response(200, json={"name": "Aziza", "username": "aziza_uz", "id": str(IGSID)})
        return httpx.Response(404, json={"error": {"message": f"unexpected {path}"}})


@pytest.fixture
def graph():
    fake = FakeGraph()
    ig._transport = httpx.MockTransport(fake.handler)
    yield fake
    ig._transport = None


@pytest.fixture
async def client(runtime):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


@pytest.fixture
async def ig_channel(session):
    shop = await make_shop(session)
    products = await make_catalog(session, shop.id)
    channel = Channel(
        shop_id=shop.id,
        type="instagram",
        external_id=IG_ID,
        display_name="@dilnoza_style",
        token_encrypted=encrypt("long-token"),
        token_expires_at=datetime.now(UTC) + timedelta(days=50),
        can_reply=True,
        is_enabled=True,
    )
    session.add(channel)
    await session.commit()
    return {"shop": shop, "channel": channel, **products}


def signed(payload: dict, secret: str = "ig-app-secret") -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}


def dm(mid: str, text: str | None = None, *, echo: bool = False, attachments: list | None = None) -> dict:
    message: dict = {"mid": mid}
    if text is not None:
        message["text"] = text
    if attachments:
        message["attachments"] = attachments
    if echo:
        message["is_echo"] = True
    sender, recipient = (IG_ID, str(IGSID)) if echo else (str(IGSID), IG_ID)
    return {
        "object": "instagram",
        "entry": [
            {
                "id": IG_ID,
                "time": 1,
                "messaging": [
                    {"sender": {"id": sender}, "recipient": {"id": recipient}, "timestamp": 1, "message": message}
                ],
            }
        ],
    }


async def post_dm(client, payload, secret="ig-app-secret"):
    body, headers = signed(payload, secret)
    return await client.post("/ig/webhook", content=body, headers=headers)


async def test_webhook_verification(client):
    ok = await client.get(
        "/ig/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "ig-verify", "hub.challenge": "42"}
    )
    assert ok.status_code == 200 and ok.text == "42"
    bad = await client.get(
        "/ig/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"}
    )
    assert bad.status_code == 403


async def test_webhook_rejects_bad_signature(client, ig_channel, session):
    resp = await post_dm(client, dm("mid.1", "Salom"), secret="wrong")
    assert resp.status_code == 403
    assert await session.scalar(select(Message)) is None


async def test_instagram_dm_to_ai_reply(client, session, runtime, fake_llm, graph, ig_channel):
    dress = ig_channel["dress"]
    fake_llm.steps = [
        tool_response("send_product_photos", {"product_id": dress.id}),
        text_response("Ha, bor! Narxi 250 000 so'm."),
    ]
    assert (await post_dm(client, dm("mid.in.1", "Qora ko'ylak bormi?"))).json() == {"ok": True}
    # Takroriy yetkazish e'tiborsiz qoldiriladi
    await post_dm(client, dm("mid.in.1", "Qora ko'ylak bormi?"))

    customer = await session.scalar(select(Customer))
    assert customer.external_user_id == IGSID and customer.name == "Aziza" and customer.username == "aziza_uz"
    msgs = (await session.scalars(select(Message).where(Message.role == "customer"))).all()
    assert len(msgs) == 1 and msgs[0].media["mid"] == "mid.in.1"

    conv = await session.scalar(select(Conversation))
    token = await runtime.redis.get(debounce_key(conv.id))
    assert await process_conversation({}, conv.id, token) == "replied"

    sent = graph.sent_messages()
    assert any(m.get("sender_action") == "typing_on" for m in sent)
    images = [m for m in sent if "attachment" in m.get("message", {})]
    assert images[0]["message"]["attachment"]["payload"]["url"] == "https://example.com/dress1.jpg"
    texts = [m["message"]["text"] for m in sent if "text" in m.get("message", {})]
    assert texts[-1] == "Ha, bor! Narxi 250 000 so'm." and all(m["recipient"]["id"] == str(IGSID) for m in sent)
    auth = [r.headers["authorization"] for r in graph.requests if r.url.path.endswith("/messages")]
    assert auth and all(a == "Bearer long-token" for a in auth)
    assert all(f"/{IG_ID}/messages" in r.url.path for r in graph.requests if r.url.path.endswith("/messages"))

    # O'zimiz yuborgan xabarning echo'si — e'tiborsiz; sotuvchi qo'lda yozgani — AI jim turadi
    own_mid = f"mid.out.{graph.counter}"
    await post_dm(client, dm(own_mid, "Ha, bor! Narxi 250 000 so'm.", echo=True))
    assert await session.scalar(select(Message).where(Message.role == "staff")) is None
    await post_dm(client, dm("mid.manual.1", "Assalomu alaykum, men sotuvchiman", echo=True))
    staff = await session.scalar(select(Message).where(Message.role == "staff"))
    assert staff.content == "Assalomu alaykum, men sotuvchiman"
    await session.refresh(conv)
    assert conv.status == "human"


async def test_instagram_attachments(client, session, ig_channel, graph):
    await post_dm(
        client,
        dm("mid.img", "shu bormi?", attachments=[{"type": "image", "payload": {"url": "https://cdn.ig/x.jpg"}}]),
    )
    await post_dm(client, dm("mid.voice", attachments=[{"type": "audio", "payload": {"url": "https://cdn.ig/v.mp4"}}]))
    msgs = (await session.scalars(select(Message).order_by(Message.id))).all()
    assert msgs[0].content == "[Rasm yubordi] shu bormi?" and msgs[0].media["url"] == "https://cdn.ig/x.jpg"
    assert msgs[1].media["type"] == "voice" and msgs[1].media["url"] == "https://cdn.ig/v.mp4"


async def test_unknown_account_is_ignored(client, session):
    payload = dm("mid.x", "Salom")
    payload["entry"][0]["id"] = "999"
    assert (await post_dm(client, payload)).status_code == 200
    assert await session.scalar(select(Message)) is None


async def test_split_long_text():
    parts = ig.split_text(("Bu uzun gap. " * 200).strip())
    assert len(parts) > 1 and all(len(p) <= ig.TEXT_LIMIT for p in parts)
    assert ig.split_text("qisqa") == ["qisqa"]


async def test_order_status_notice_respects_24h_window(client, session, runtime, graph, ig_channel):
    from app.telegram.handlers import notify_customer_about_order

    await post_dm(client, dm("mid.o1", "Olaman"))
    conv = await session.scalar(select(Conversation))
    customer = await session.get(Customer, conv.customer_id)
    await cart_svc.update_cart(session, conv, "add", ig_channel["bag"].variants[0].id, 1)
    settings = await session.get(ShopSettings, ig_channel["shop"].id)
    order = await create_order(
        session, conv=conv, customer=customer, settings=settings, name="A", phone="+998901234567", address="Toshkent"
    )
    order.status = "confirmed"
    await session.commit()
    await notify_customer_about_order(session, order)
    assert "tasdiqlandi" in graph.sent_messages()[-1]["message"]["text"]

    before = len(graph.sent_messages())
    conv.last_message_at = datetime.now(UTC) - timedelta(hours=30)
    order.status = "shipped"
    await session.commit()
    await notify_customer_about_order(session, order)
    assert len(graph.sent_messages()) == before  # oyna yopiq — yuborilmadi
    assert await session.scalar(select(Order.status)) == "shipped"


REG = {"name": "Dilnoza", "phone": "90 123 45 67", "password": "juda-maxfiy-1", "shop_name": "Dilnoza Style"}


async def test_oauth_connect_flow(client, session, graph):
    await client.post("/api/auth/register", json=REG)
    ch = (await client.get("/api/channels")).json()
    assert ch["instagram_configured"] and ch["instagram_allowed"] and ch["instagram"] is None

    url = (await client.post("/api/instagram/connect")).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["client_id"] == ["ig-app-id"] and "instagram_business_manage_messages" in q["scope"][0]
    assert q["redirect_uri"][0].endswith("/api/instagram/callback")

    resp = await client.get("/api/instagram/callback", params={"code": "abc#_", "state": q["state"][0]})
    assert resp.status_code == 302 and resp.headers["location"].endswith("/app/connect?instagram=ok")
    channel = await session.scalar(select(Channel).where(Channel.type == "instagram"))
    assert channel.external_id == IG_ID and channel.display_name == "@dilnoza_style"
    assert decrypt(channel.token_encrypted) == "long-token" and channel.token_encrypted != "long-token"
    assert channel.token_expires_at > datetime.now(UTC) + timedelta(days=55)
    code_req = next(r for r in graph.requests if r.url.path == "/oauth/access_token")
    assert parse_qs(code_req.content.decode())["code"] == ["abc"]
    assert any(r.url.path.endswith("/me/subscribed_apps") for r in graph.requests)

    ch = (await client.get("/api/channels")).json()
    assert ch["instagram"]["display_name"] == "@dilnoza_style"

    # State bir martalik
    again = await client.get("/api/instagram/callback", params={"code": "abc", "state": q["state"][0]})
    assert again.headers["location"].endswith("instagram=error")

    assert (await client.delete("/api/instagram")).status_code == 204
    assert (await client.get("/api/channels")).json()["instagram"] is None


async def test_same_instagram_cannot_join_two_shops(client, session, graph, ig_channel):
    await client.post("/api/auth/register", json={**REG, "phone": "93 111 22 33", "shop_name": "Boshqa"})
    state = parse_qs(urlparse((await client.post("/api/instagram/connect")).json()["url"]).query)["state"][0]
    resp = await client.get("/api/instagram/callback", params={"code": "abc", "state": state})
    assert resp.headers["location"].endswith("instagram=taken")


async def test_connect_requires_plan_and_config(client, session, monkeypatch):
    from app.config import get_settings
    from app.models import Shop

    await client.post("/api/auth/register", json=REG)
    shop = await session.scalar(select(Shop))
    shop.plan = "start"
    await session.commit()
    assert (await client.post("/api/instagram/connect")).status_code == 402
    monkeypatch.setattr(get_settings(), "ig_app_id", "")
    assert (await client.post("/api/instagram/connect")).status_code == 503


async def test_refresh_expiring_tokens(session, runtime, graph, ig_channel):
    channel = ig_channel["channel"]
    channel.token_expires_at = datetime.now(UTC) + timedelta(days=5)
    await session.commit()
    assert await refresh_instagram_tokens({}) == "refreshed=1 failed=0"
    await session.refresh(channel)
    assert decrypt(channel.token_encrypted) == "long-token-2"
    assert channel.token_expires_at > datetime.now(UTC) + timedelta(days=50)
    assert await refresh_instagram_tokens({}) == "refreshed=0 failed=0"
