import time
from urllib.parse import parse_qs, urlparse

import pytest
from aiogram.methods import SendMessage
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import create_app
from app.models import Account, Shop, ShopUser
from app.services.auth import LOGIN_ATTEMPTS
from app.telegram.bot import build_dispatcher
from tests.factories import OWNER_ID, make_shop

REG = {"name": "Dilnoza", "phone": "90 123 45 67", "password": "juda-maxfiy-1", "shop_name": "Dilnoza Style"}


@pytest.fixture
async def client(runtime):
    app = create_app()
    app.state.dispatcher = build_dispatcher()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def register(client, **overrides):
    return await client.post("/api/auth/register", json={**REG, **overrides})


async def test_register_creates_account_shop_and_session(client, session):
    resp = await register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["phone"] == "+998901234567" and body["shops"][0]["name"] == "Dilnoza Style"
    assert body["shops"][0]["role"] == "owner" and not body["telegram_linked"]
    assert "nv_session" in resp.cookies
    account = await session.scalar(select(Account))
    assert account.password_hash.startswith("$argon2") and "juda-maxfiy" not in account.password_hash

    # Sessiya bilan panel API'lari ishlaydi
    me = (await client.get("/api/me")).json()
    assert me["shop"]["name"] == "Dilnoza Style" and me["telegram_user_id"] is None
    settings = await client.get("/api/settings")
    assert settings.status_code == 200


async def test_register_validation(client):
    assert (await register(client, phone="123")).status_code == 422
    assert (await register(client, password="short")).status_code == 422
    assert (await register(client)).status_code == 201
    assert (await register(client, phone="+998901234567")).status_code == 409


async def test_login_logout_and_bad_password(client):
    await register(client)
    await client.post("/api/auth/logout")
    client.cookies.clear()
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await client.get("/api/products")).status_code == 401

    bad = await client.post("/api/auth/login", json={"phone": "901234567", "password": "wrong-pass"})
    assert bad.status_code == 401
    ok = await client.post("/api/auth/login", json={"phone": "+998 (90) 123-45-67", "password": REG["password"]})
    assert ok.status_code == 200 and ok.json()["name"] == "Dilnoza"
    assert (await client.get("/api/products")).status_code == 200


async def test_login_rate_limit(client):
    await register(client)
    client.cookies.clear()
    for _ in range(LOGIN_ATTEMPTS):
        await client.post("/api/auth/login", json={"phone": "901234567", "password": "nope-nope"})
    blocked = await client.post("/api/auth/login", json={"phone": "901234567", "password": REG["password"]})
    assert blocked.status_code == 429


async def test_tampered_session_is_rejected(client):
    await register(client)
    token = client.cookies["nv_session"]
    client.cookies.clear()
    client.cookies.set("nv_session", token[:-3] + "abc")
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_shop_isolation_between_accounts(client, session):
    await register(client)
    await client.post("/api/products", json={"name": "Maxfiy mahsulot", "price": 1000})
    client.cookies.clear()
    await register(client, phone="93 000 00 00", shop_name="Boshqa do'kon")
    assert (await client.get("/api/products")).json() == []
    other_shop = await session.scalar(select(Shop).where(Shop.name == "Dilnoza Style"))
    resp = await client.get("/api/products", headers={"X-Shop-Id": str(other_shop.id)})
    assert resp.status_code == 403


async def test_change_password_and_profile(client):
    await register(client)
    bad = await client.post("/api/auth/password", json={"old_password": "x", "new_password": "yangi-parol-2"})
    assert bad.status_code == 403
    ok = await client.post(
        "/api/auth/password", json={"old_password": REG["password"], "new_password": "yangi-parol-2"}
    )
    assert ok.status_code == 200
    prof = (await client.patch("/api/auth/me", json={"lang": "ru", "name": "Dilya"})).json()
    assert prof["lang"] == "ru" and prof["name"] == "Dilya"
    client.cookies.clear()
    login = await client.post("/api/auth/login", json={"phone": "901234567", "password": "yangi-parol-2"})
    assert login.status_code == 200


def tg_command(text: str, user_id: int = OWNER_ID) -> dict:
    cmd = text.split()[0]
    return {
        "update_id": int(time.time() * 1000) % 10**9,
        "message": {
            "message_id": 1,
            "date": int(time.time()),
            "chat": {"id": user_id, "type": "private", "first_name": "D"},
            "from": {"id": user_id, "is_bot": False, "first_name": "D"},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(cmd)}],
        },
    }


async def post_tg(client, payload):
    return await client.post(
        "/tg/webhook/hook-secret", json=payload, headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret"}
    )


async def test_link_telegram_merges_bot_created_shop(client, session, fake_bot):
    # Sotuvchi avval botda /start bosgan (bot orqali do'kon yaratilgan)
    bot_shop = await make_shop(session, "Bot do'koni")
    await session.commit()
    await register(client)
    link = (await client.post("/api/auth/telegram-link")).json()["url"]
    token = link.split("start=")[1]
    await post_tg(client, tg_command(f"/start {token}"))
    assert "ulandi" in fake_bot.sent(SendMessage)[-1].text

    me = (await client.get("/api/auth/me")).json()
    assert me["telegram_linked"] and {s["name"] for s in me["shops"]} == {"Dilnoza Style", "Bot do'koni"}
    rows = (await session.scalars(select(ShopUser).where(ShopUser.telegram_user_id == OWNER_ID))).all()
    assert len(rows) == 2 and all(r.account_id for r in rows)
    assert bot_shop.id in {r.shop_id for r in rows}

    # Token bir martalik
    await post_tg(client, tg_command(f"/start {token}"))
    assert "eskirgan" in fake_bot.sent(SendMessage)[-1].text


async def test_magic_link_login_for_bot_first_seller(client, session, fake_bot):
    await make_shop(session, "Bot do'koni")
    await session.commit()
    await post_tg(client, tg_command("/web"))
    text = fake_bot.sent(SendMessage)[-1].text
    url = next(w for w in text.split() if w.startswith("https://navbatchi.test/app/magic"))
    token = parse_qs(urlparse(url).query)["token"][0]

    resp = await client.post("/api/auth/magic", json={"token": token})
    assert resp.status_code == 200
    me = resp.json()
    assert me["telegram_linked"] and not me["has_password"] and me["shops"][0]["name"] == "Bot do'koni"
    assert (await client.post("/api/auth/magic", json={"token": token})).status_code == 401

    # Parol o'rnatish (telefon bilan) → keyin telefon + parol bilan kirish
    set_pw = await client.post("/api/auth/password", json={"new_password": "parol-12345", "phone": "97 111 22 33"})
    assert set_pw.status_code == 200 and set_pw.json()["phone"] == "+998971112233"
    client.cookies.clear()
    ok = await client.post("/api/auth/login", json={"phone": "971112233", "password": "parol-12345"})
    assert ok.status_code == 200


async def test_web_command_requires_shop(client, fake_bot):
    await post_tg(client, tg_command("/web", user_id=31337))
    assert "do'kon yo'q" in fake_bot.sent(SendMessage)[-1].text


async def test_platform_admin_endpoints(client, session):
    await register(client)
    assert (await client.get("/api/admin/shops")).status_code == 403
    account = await session.scalar(select(Account))
    account.is_platform_admin = True
    await session.commit()

    shops = (await client.get("/api/admin/shops")).json()
    assert shops[0]["name"] == "Dilnoza Style" and shops[0]["owner_phone"] == "+998901234567"
    shop_id = shops[0]["id"]

    detail = (
        await client.post(
            f"/api/admin/shops/{shop_id}/payments",
            json={"plan": "business", "months": 2, "amount": 598000, "note": "chek #12"},
        )
    ).json()
    assert detail["shop"]["plan"] == "business" and detail["shop"]["paid_until"]
    assert detail["payments"][0]["amount"] == 598000

    overview = (await client.get("/api/admin/overview")).json()
    assert overview["paying"] == 1 and overview["mrr"] == 299000 and overview["month_revenue"] == 598000

    paused = (await client.post(f"/api/admin/shops/{shop_id}/status", json={"status": "paused"})).json()
    assert paused["status"] == "paused"
    trial = (await client.post(f"/api/admin/shops/{shop_id}/plan", json={"trial_days": 7})).json()
    assert trial["trial_ends_at"]


async def test_channels_and_daily_stats(client):
    await register(client)
    ch = (await client.get("/api/channels")).json()
    assert ch["business_connected"] is False and ch["bot_link"].endswith("?start=shop_1")
    daily = (await client.get("/api/stats/daily?days=7")).json()
    assert len(daily) == 7 and all(p["orders"] == 0 for p in daily)
