from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import create_app
from app.models import Account, Shop, ShopUser
from app.telegram.bot import build_dispatcher
from app.telegram.notify import notify_shop, shop_recipients

OWNER = {"name": "Dilnoza", "phone": "90 123 45 67", "password": "juda-maxfiy-1", "shop_name": "Dilnoza Style"}
STAFF_PHONE = "+998 91 555 44 33"


@pytest.fixture
async def app(runtime):
    app = create_app()
    app.state.dispatcher = build_dispatcher()
    return app


def client_for(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def owner(app):
    async with client_for(app) as c:
        assert (await c.post("/api/auth/register", json=OWNER)).status_code == 201
        yield c


def invite_token(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


async def invite_operator(owner) -> dict:
    resp = await owner.post("/api/staff", json={"name": "Aziz", "phone": STAFF_PHONE})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_invite_accept_and_operator_permissions(app, owner, session):
    staff = await invite_operator(owner)
    assert staff["role"] == "operator" and staff["pending"] and staff["phone"] == "+998915554433"
    assert staff["invite_url"].startswith("https://navbatchi.test/app/invite?token=")
    token = invite_token(staff["invite_url"])

    listing = (await owner.get("/api/staff")).json()
    assert [(m["name"], m["role"], m["is_me"]) for m in listing] == [
        ("Dilnoza", "owner", True),
        ("Aziz", "operator", False),
    ]

    async with client_for(app) as op:
        # Parolsiz akkaunt bilan kirib bo'lmaydi
        login = await op.post("/api/auth/login", json={"phone": STAFF_PHONE, "password": "anything-123"})
        assert login.status_code == 401

        info = await op.get("/api/auth/invite", params={"token": token})
        assert info.json() == {"name": "Aziz", "phone": "+998915554433", "shops": ["Dilnoza Style"]}
        assert (await op.post("/api/auth/invite", json={"token": token, "password": "short"})).status_code == 422
        accepted = await op.post("/api/auth/invite", json={"token": token, "password": "operator-parol-1"})
        assert accepted.status_code == 200
        assert accepted.json()["shops"][0]["role"] == "operator"
        # Havola bir martalik
        assert (
            await op.post("/api/auth/invite", json={"token": token, "password": "boshqa-parol-2"})
        ).status_code == 401

        # Operator: kundalik ish — ha; sozlamalar, to'lov, xodimlar — yo'q
        assert (await op.get("/api/orders")).status_code == 200
        assert (await op.get("/api/leads")).status_code == 200
        assert (await op.get("/api/conversations")).status_code == 200
        assert (await op.post("/api/products", json={"name": "Sumka", "price": 100_000})).status_code == 201
        settings = (await op.get("/api/settings")).json()
        assert (await op.put("/api/settings", json=settings)).status_code == 403
        assert (await op.put("/api/shop", json={"name": "Buzildi"})).status_code == 403
        assert (await op.get("/api/staff")).status_code == 403
        assert (await op.post("/api/staff", json={"name": "X", "phone": "901112233"})).status_code == 403
        checkout = await op.post("/api/billing/checkout", json={"plan": "start", "provider": "payme"})
        assert checkout.status_code == 403

    # Endi oddiy login ishlaydi
    async with client_for(app) as op2:
        login = await op2.post("/api/auth/login", json={"phone": STAFF_PHONE, "password": "operator-parol-1"})
        assert login.status_code == 200
    listing = (await owner.get("/api/staff")).json()
    assert not listing[1]["pending"]
    assert (await owner.post(f"/api/staff/{staff['id']}/invite")).status_code == 409


async def test_existing_account_is_added_without_invite(app, owner, session):
    async with client_for(app) as other:
        reg = {**OWNER, "name": "Aziz", "phone": STAFF_PHONE, "shop_name": "Aziz Shop"}
        assert (await other.post("/api/auth/register", json=reg)).status_code == 201
        staff = await invite_operator(owner)
        assert staff["invite_url"] is None and not staff["pending"]
        me = (await other.get("/api/auth/me")).json()
        assert [(s["name"], s["role"]) for s in me["shops"]] == [("Dilnoza Style", "operator"), ("Aziz Shop", "owner")]
    assert (await owner.post("/api/staff", json={"name": "Aziz", "phone": STAFF_PHONE})).status_code == 409
    assert (await owner.post("/api/staff", json={"name": "Aziz", "phone": "123"})).status_code == 422


async def test_roles_and_removal_rules(owner, session):
    listing = (await owner.get("/api/staff")).json()
    me = listing[0]["id"]
    # Yagona egani operatorga tushirib ham, o'chirib ham bo'lmaydi
    assert (await owner.patch(f"/api/staff/{me}", json={"role": "operator"})).status_code == 422
    assert (await owner.delete(f"/api/staff/{me}")).status_code == 422

    staff = await invite_operator(owner)
    promoted = await owner.patch(f"/api/staff/{staff['id']}", json={"role": "owner", "notify": False})
    assert promoted.json()["role"] == "owner" and promoted.json()["notify"] is False
    reissued = (await owner.post(f"/api/staff/{staff['id']}/invite")).json()
    assert reissued["invite_url"] and reissued["pending"]

    assert (await owner.delete(f"/api/staff/{staff['id']}")).status_code == 204
    assert [m["name"] for m in (await owner.get("/api/staff")).json()] == ["Dilnoza"]
    # Akkaunt qoladi, faqat do'kondan chiqariladi
    assert await session.scalar(select(Account).where(Account.phone == "+998915554433")) is not None
    assert (await owner.delete("/api/staff/99999")).status_code == 404


async def test_other_shop_member_is_not_reachable(app, owner):
    async with client_for(app) as other:
        reg = {**OWNER, "phone": "93 000 00 00", "shop_name": "Boshqa"}
        assert (await other.post("/api/auth/register", json=reg)).status_code == 201
        foreign = (await other.get("/api/staff")).json()[0]["id"]
    assert (await owner.patch(f"/api/staff/{foreign}", json={"notify": False})).status_code == 404
    assert (await owner.delete(f"/api/staff/{foreign}")).status_code == 404


async def test_notifications_reach_linked_staff_only(owner, session, fake_bot):
    await invite_operator(owner)
    shop = await session.scalar(select(Shop))
    members = (await session.scalars(select(ShopUser).order_by(ShopUser.id))).all()
    # Egasi Telegram ulamagan, operator ulagan
    members[1].telegram_user_id = 4242
    session.add(ShopUser(shop_id=shop.id, telegram_user_id=5151, name="Jim", role="operator", notify=False))
    await session.commit()
    assert await shop_recipients(session, shop.id) == [4242]
    await notify_shop(fake_bot, session, shop.id, "Yangi buyurtma")
    assert [m.chat_id for m in fake_bot.sent()] == [4242]
