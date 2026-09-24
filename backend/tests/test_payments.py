import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.main import create_app
from app.models import Payment, Shop, Subscription
from app.payments import payme
from app.services.billing import BillingError, activate_subscription, plan_price
from app.telegram.bot import build_dispatcher

REG = {"name": "Dilnoza", "phone": "90 123 45 67", "password": "juda-maxfiy-1", "shop_name": "Dilnoza Style"}
PAYME_AUTH = {"Authorization": "Basic " + base64.b64encode(b"Paycom:payme-key").decode()}


@pytest.fixture
async def client(runtime):
    app = create_app()
    app.state.dispatcher = build_dispatcher()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/api/auth/register", json=REG)).status_code == 201
        yield c


async def checkout(client, provider: str, plan: str = "business", months: int = 1) -> dict:
    resp = await client.post("/api/billing/checkout", json={"plan": plan, "months": months, "provider": provider})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def rpc(client, method: str, params: dict, auth: dict | None = None) -> dict:
    body = {"jsonrpc": "2.0", "id": 7, "method": method, "params": params}
    resp = await client.post("/api/payments/payme", json=body, headers=PAYME_AUTH if auth is None else auth)
    assert resp.status_code == 200
    return resp.json()


def test_plan_price():
    assert plan_price("business", 1) == 299_000
    assert plan_price("business", 3) == 897_000
    assert plan_price("start", 12) == round(149_000 * 12 * 0.8)
    with pytest.raises(BillingError):
        plan_price("trial", 1)
    with pytest.raises(BillingError):
        plan_price("pro", 2)


async def test_billing_info_and_checkout_urls(client):
    info = (await client.get("/api/billing")).json()
    assert info["plan"] == "trial" and info["providers"] == ["payme", "click"]
    assert [p["code"] for p in info["plans"]] == ["start", "business", "pro"] and info["payments"] == []

    pm = await checkout(client, "payme", months=12)
    assert pm["amount"] == plan_price("business", 12)
    encoded = pm["url"].removeprefix("https://checkout.paycom.uz/")
    decoded = dict(part.split("=", 1) for part in base64.b64decode(encoded).decode().split(";"))
    assert decoded["m"] == "payme-merchant" and decoded["ac.order_id"] == str(pm["payment_id"])
    assert decoded["a"] == str(pm["amount"] * 100) and decoded["c"] == "https://navbatchi.test/app/billing?paid=1"

    ck = await checkout(client, "click")
    q = parse_qs(urlparse(ck["url"]).query)
    assert q["service_id"] == ["101"] and q["merchant_id"] == ["202"]
    assert q["amount"] == ["299000"] and q["transaction_param"] == [str(ck["payment_id"])]

    # To'lanmagan hisoblar tarixda ko'rinmaydi
    assert (await client.get("/api/billing")).json()["payments"] == []


async def test_checkout_unconfigured_provider(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "payme_key", "")
    resp = await client.post("/api/billing/checkout", json={"plan": "start", "provider": "payme"})
    assert resp.status_code == 503
    bad = await client.post("/api/billing/checkout", json={"plan": "trial", "provider": "click"})
    assert bad.status_code == 422


# ---------------------------------------------------------------- Payme


async def test_payme_auth_and_unknown_method(client):
    wrong = {"Authorization": "Basic " + base64.b64encode(b"Paycom:wrong").decode()}
    assert (await rpc(client, "CheckTransaction", {"id": "x"}, auth=wrong))["error"]["code"] == payme.ERR_AUTH
    assert (await rpc(client, "CheckTransaction", {"id": "x"}, auth={}))["error"]["code"] == payme.ERR_AUTH
    assert (await rpc(client, "Nope", {}))["error"]["code"] == payme.ERR_METHOD
    bad_json = await client.post("/api/payments/payme", content=b"{", headers=PAYME_AUTH)
    assert bad_json.json()["error"]["code"] == payme.ERR_PARSE


async def test_payme_full_flow(client, session):
    inv = await checkout(client, "payme", plan="business", months=3)
    account = {"order_id": str(inv["payment_id"])}
    tiyin = inv["amount"] * 100

    assert (await rpc(client, "CheckPerformTransaction", {"amount": tiyin, "account": account}))["result"] == {
        "allow": True
    }
    wrong = await rpc(client, "CheckPerformTransaction", {"amount": tiyin - 100, "account": account})
    assert wrong["error"]["code"] == payme.ERR_AMOUNT
    missing = await rpc(client, "CheckPerformTransaction", {"amount": tiyin, "account": {"order_id": "999"}})
    assert missing["error"]["code"] == payme.ERR_ORDER_NOT_FOUND

    t = 1_700_000_000_000
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    params = {"id": "pm-1", "time": now_ms, "amount": tiyin, "account": account}
    created = (await rpc(client, "CreateTransaction", params))["result"]
    assert created["state"] == 1 and created["transaction"] == str(inv["payment_id"])
    # Idempotent: xuddi shu id qayta kelsa — o'sha javob
    assert (await rpc(client, "CreateTransaction", params))["result"] == created
    # Boshqa tranzaksiya shu buyurtma uchun — band
    other = await rpc(client, "CreateTransaction", {**params, "id": "pm-2"})
    assert other["error"]["code"] == payme.ERR_ORDER_BUSY
    busy = await rpc(client, "CheckPerformTransaction", {"amount": tiyin, "account": account})
    assert busy["error"]["code"] == payme.ERR_ORDER_BUSY

    performed = (await rpc(client, "PerformTransaction", {"id": "pm-1"}))["result"]
    assert performed["state"] == 2 and performed["perform_time"] > 0
    # Qayta Perform — o'sha natija, obuna ikki marta berilmaydi
    assert (await rpc(client, "PerformTransaction", {"id": "pm-1"}))["result"] == performed

    shop = await session.scalar(select(Shop))
    assert shop.plan == "business" and shop.status == "active"
    subs = (await session.scalars(select(Subscription))).all()
    assert len(subs) == 1 and (subs[0].period_end - subs[0].period_start) == timedelta(days=90)

    check = (await rpc(client, "CheckTransaction", {"id": "pm-1"}))["result"]
    assert check["state"] == 2 and check["create_time"] == now_ms and check["cancel_time"] == 0
    cancel = await rpc(client, "CancelTransaction", {"id": "pm-1", "reason": 5})
    assert cancel["error"]["code"] == payme.ERR_CANNOT_CANCEL
    assert (await rpc(client, "CheckTransaction", {"id": "nope"}))["error"]["code"] == payme.ERR_NOT_FOUND

    statement = (await rpc(client, "GetStatement", {"from": t, "to": now_ms + 1000}))["result"]["transactions"]
    assert [(x["id"], x["amount"], x["state"]) for x in statement] == [("pm-1", tiyin, 2)]
    assert statement[0]["account"] == account

    info = (await client.get("/api/billing")).json()
    assert info["plan"] == "business" and info["paid_until"] is not None
    assert [(p["provider"], p["status"], p["months"]) for p in info["payments"]] == [("payme", "paid", 3)]


async def test_payme_cancel_before_perform(client, session):
    inv = await checkout(client, "payme", plan="start")
    params = {"id": "pm-c", "time": 1, "amount": inv["amount"] * 100, "account": {"order_id": str(inv["payment_id"])}}
    # time=1 — juda eski, lekin Create yangi tranzaksiya uchun faqat vaqtni yozadi
    assert (await rpc(client, "CreateTransaction", params))["result"]["state"] == 1
    cancelled = (await rpc(client, "CancelTransaction", {"id": "pm-c", "reason": 3}))["result"]
    assert cancelled["state"] == -1 and cancelled["cancel_time"] > 0
    # Qayta bekor qilish — o'sha holat
    assert (await rpc(client, "CancelTransaction", {"id": "pm-c", "reason": 3}))["result"]["state"] == -1
    perform = await rpc(client, "PerformTransaction", {"id": "pm-c"})
    assert perform["error"]["code"] == payme.ERR_CANNOT_PERFORM
    check = (await rpc(client, "CheckTransaction", {"id": "pm-c"}))["result"]
    assert check["state"] == -1 and check["reason"] == 3
    shop = await session.scalar(select(Shop))
    assert shop.plan == "trial"


async def test_payme_expired_transaction_is_cancelled(client, session):
    inv = await checkout(client, "payme", plan="start")
    old = int((datetime.now(UTC) - timedelta(hours=13)).timestamp() * 1000)
    params = {
        "id": "pm-old",
        "time": old,
        "amount": inv["amount"] * 100,
        "account": {"order_id": str(inv["payment_id"])},
    }
    assert (await rpc(client, "CreateTransaction", params))["result"]["state"] == 1
    perform = await rpc(client, "PerformTransaction", {"id": "pm-old"})
    assert perform["error"]["code"] == payme.ERR_CANNOT_PERFORM
    check = (await rpc(client, "CheckTransaction", {"id": "pm-old"}))["result"]
    assert check["state"] == -1 and check["reason"] == payme.REASON_TIMEOUT
    payment = await session.get(Payment, inv["payment_id"])
    assert payment.status == "cancelled"


async def test_payme_rejects_click_invoice(client):
    inv = await checkout(client, "click")
    resp = await rpc(
        client,
        "CheckPerformTransaction",
        {"amount": inv["amount"] * 100, "account": {"order_id": str(inv["payment_id"])}},
    )
    assert resp["error"]["code"] == payme.ERR_ORDER_NOT_FOUND


# ---------------------------------------------------------------- Click


def click_form(payment_id: int, amount, action: int, prepare_id: int | None = None, **extra) -> dict:
    form = {
        "click_trans_id": "555",
        "service_id": "101",
        "click_paydoc_id": "9",
        "merchant_trans_id": str(payment_id),
        "amount": str(amount),
        "action": str(action),
        "error": "0",
        "error_note": "Success",
        "sign_time": "2026-09-24 10:00:00",
    }
    if prepare_id is not None:
        form["merchant_prepare_id"] = str(prepare_id)
    form.update(extra)
    raw = form["click_trans_id"] + form["service_id"] + "click-secret" + form["merchant_trans_id"]
    if prepare_id is not None:
        raw += form["merchant_prepare_id"]
    raw += form["amount"] + form["action"] + form["sign_time"]
    form.setdefault("sign_string", hashlib.md5(raw.encode()).hexdigest())  # noqa: S324
    return form


async def test_click_prepare_complete(client, session):
    inv = await checkout(client, "click", plan="pro", months=12)
    pid, amount = inv["payment_id"], inv["amount"]

    prep = (await client.post("/api/payments/click/prepare", data=click_form(pid, f"{amount}.00", 0))).json()
    assert prep["error"] == 0 and prep["merchant_prepare_id"] == pid

    done = (await client.post("/api/payments/click/complete", data=click_form(pid, amount, 1, prepare_id=pid))).json()
    assert done["error"] == 0 and done["merchant_confirm_id"] == pid
    shop = await session.scalar(select(Shop))
    assert shop.plan == "pro"
    sub = await session.scalar(select(Subscription))
    assert sub.period_end - sub.period_start == timedelta(days=360)

    again = (await client.post("/api/payments/click/complete", data=click_form(pid, amount, 1, prepare_id=pid))).json()
    assert again["error"] == -4
    assert len((await session.scalars(select(Subscription))).all()) == 1


async def test_click_errors(client, session):
    inv = await checkout(client, "click")
    pid, amount = inv["payment_id"], inv["amount"]
    post = client.post
    bad_sign = (await post("/api/payments/click/prepare", data=click_form(pid, amount, 0, sign_string="x"))).json()
    assert bad_sign["error"] == -1
    assert (await post("/api/payments/click/prepare", data=click_form(pid, amount + 1, 0))).json()["error"] == -2
    assert (await post("/api/payments/click/prepare", data=click_form(pid, amount, 1))).json()["error"] == -3
    assert (await post("/api/payments/click/prepare", data=click_form(999, amount, 0))).json()["error"] == -5
    assert (await post("/api/payments/click/prepare", data={"amount": "1"})).json()["error"] == -8
    wrong_prep = click_form(pid, amount, 1, prepare_id=pid)
    assert (await post("/api/payments/click/complete", data=wrong_prep)).json()["error"] == -6  # prepare bo'lmagan

    assert (await post("/api/payments/click/prepare", data=click_form(pid, amount, 0))).json()["error"] == 0
    failed = click_form(pid, amount, 1, prepare_id=pid, error="-5017")
    assert (await post("/api/payments/click/complete", data=failed)).json()["error"] == -9
    payment = await session.get(Payment, pid)
    assert payment.status == "cancelled"
    retry = (await post("/api/payments/click/complete", data=click_form(pid, amount, 1, prepare_id=pid))).json()
    assert retry["error"] == -9
    shop = await session.scalar(select(Shop))
    assert shop.plan == "trial"


async def test_subscription_extends_from_paid_until(session, runtime):
    from tests.factories import make_shop

    shop = await make_shop(session)
    first = await activate_subscription(session, shop, "start", 1)
    second = await activate_subscription(session, shop, "business", 1)
    assert second.period_start == first.period_end
    assert shop.plan == "business"
