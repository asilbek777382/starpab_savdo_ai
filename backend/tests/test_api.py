import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import create_app
from app.models import Lead
from app.services.catalog_import import template_xlsx
from tests.factories import OWNER_ID, init_data, make_shop
from tests.fakes import text_response, tool_response


@pytest.fixture
async def client(runtime):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


@pytest.fixture
async def shop(session):
    shop = await make_shop(session)
    await session.commit()
    return shop


AUTH = {"Authorization": f"tma {init_data(OWNER_ID)}"}


async def test_auth_required(client, shop):
    assert (await client.get("/api/me")).status_code == 401
    assert (await client.get("/api/me", headers={"Authorization": "tma bad"})).status_code == 401
    stranger = {"Authorization": f"tma {init_data(999)}"}
    assert (await client.get("/api/me", headers=stranger)).status_code == 403
    me = (await client.get("/api/me", headers=AUTH)).json()
    assert me["shop"]["name"] == "Dilnoza Style" and me["bot_link"].endswith(f"shop_{shop.id}")


async def test_settings_roundtrip_with_modes(client, shop):
    settings = (await client.get("/api/settings", headers=AUTH)).json()
    assert settings["ai_mode"] == "sell" and len(settings["delivery_zones"]) == 2
    settings.update(ai_mode="lead", ai_tasks="Tanishtir va raqam so'ra", lead_chat_id=-100, handoff_after_lead=False)
    resp = await client.put("/api/settings", json=settings, headers=AUTH)
    assert resp.status_code == 200
    again = (await client.get("/api/settings", headers=AUTH)).json()
    assert again["ai_mode"] == "lead" and again["lead_chat_id"] == -100 and not again["handoff_after_lead"]
    settings["ai_mode"] = "unknown"
    assert (await client.put("/api/settings", json=settings, headers=AUTH)).status_code == 422


async def test_product_crud_and_import(client, shop, runtime):
    body = {
        "name": "Oq futbolka",
        "price": 90000,
        "category_name": "Futbolkalar",
        "variants": [{"attrs": {"size": "M"}, "stock": 5}, {"attrs": {"size": "L"}, "stock": 0}],
        "images": ["https://example.com/t.jpg"],
    }
    created = (await client.post("/api/products", json=body, headers=AUTH)).json()
    assert (
        created["id"] and len(created["variants"]) == 2 and created["images"][0]["url"] == "https://example.com/t.jpg"
    )

    body["price"] = 95000
    body["variants"] = [{"attrs": {"size": "XL"}, "stock": 1}]
    updated = (await client.put(f"/api/products/{created['id']}", json=body, headers=AUTH)).json()
    assert updated["price"] == 95000 and [v["attrs"]["size"] for v in updated["variants"]] == ["XL"]

    listed = (await client.get("/api/products?q=futbolka", headers=AUTH)).json()
    assert [p["id"] for p in listed] == [created["id"]]

    template = await client.get("/api/products-import-template", headers=AUTH)
    assert template.status_code == 200
    resp = await client.post("/api/products/import", files={"file": ("k.xlsx", template_xlsx())}, headers=AUTH)
    assert resp.json() == {"created": 1, "updated": 0, "errors": []}

    assert (await client.delete(f"/api/products/{created['id']}", headers=AUTH)).status_code == 204
    assert (await client.get(f"/api/products/{created['id']}", headers=AUTH)).status_code == 404


async def test_other_shop_data_is_invisible(client, shop, session):
    other = await make_shop(session, "Boshqa")
    await session.commit()
    from app.services.catalog import save_product

    p = await save_product(session, other.id, product=None, name="Yashirin", price=1)
    await session.commit()
    assert (await client.get(f"/api/products/{p.id}", headers=AUTH)).status_code == 404


async def test_test_chat_order_and_stats(client, shop, fake_llm, session):
    product = (await client.post("/api/products", json={"name": "Charm sumka", "price": 180000}, headers=AUTH)).json()
    variant_id = product["variants"][0]["id"]
    fake_llm.steps = [
        tool_response("update_cart", {"action": "add", "variant_id": variant_id, "qty": 1}),
        tool_response(
            "create_order",
            {"name": "Test", "phone": "+998901112233", "address": "Yunusobod", "customer_confirmed": True},
        ),
        text_response("Buyurtma qabul qilindi"),
    ]
    resp = (await client.post("/api/test-chat", json={"message": "Sumka olaman"}, headers=AUTH)).json()
    assert resp["status"] == "replied" and resp["order_number"] == 1
    assert resp["replies"][-1]["text"] == "Buyurtma qabul qilindi"
    assert [t["tool"] for t in resp["tools"]] == ["update_cart", "create_order"]

    orders = (await client.get("/api/orders", headers=AUTH)).json()
    assert orders[0]["total"] == 200000 and orders[0]["source"] == "test"
    resp = await client.post(f"/api/orders/{orders[0]['id']}/status", json={"status": "shipped"}, headers=AUTH)
    assert resp.json()["status"] == "shipped"
    assert (
        await client.post(f"/api/orders/{orders[0]['id']}/status", json={"status": "x"}, headers=AUTH)
    ).status_code == 422

    stats = (await client.get("/api/stats", headers=AUTH)).json()
    assert stats["orders"] == 0  # test buyurtmalari statistikaga kirmaydi
    assert stats["month_conversations"] == 1 and stats["month_limit"] == 300


async def test_test_chat_lead_and_leads_api(client, shop, fake_llm, session):
    fake_llm.steps = [
        tool_response("save_lead", {"phone": "+998935554433", "interest": "narxlar"}),
        text_response("Rahmat, operator qo'ng'iroq qiladi"),
    ]
    resp = (await client.post("/api/test-chat", json={"message": "93 555 44 33"}, headers=AUTH)).json()
    assert resp["lead_id"] and resp["handed_off"]
    leads = (await client.get("/api/leads", headers=AUTH)).json()
    assert leads[0]["phone"] == "+998935554433" and leads[0]["channel_type"] == "test"
    resp = await client.post(f"/api/leads/{leads[0]['id']}/status", json={"status": "won"}, headers=AUTH)
    assert resp.json()["status"] == "won"
    assert (await session.scalar(select(Lead.status))) == "won"

    # Suhbat operatorga o'tgan; reset bilan yangi test suhbat
    again = (await client.post("/api/test-chat", json={"message": "salom"}, headers=AUTH)).json()
    assert again["status"] == "ai_off"
    fresh = (await client.post("/api/test-chat", json={"message": "salom", "reset": True}, headers=AUTH)).json()
    assert fresh["status"] == "replied"


async def test_conversation_ai_toggle(client, shop, fake_llm):
    await client.post("/api/test-chat", json={"message": "salom"}, headers=AUTH)
    convs = (await client.get("/api/conversations", headers=AUTH)).json()
    conv_id = convs[0]["id"]
    off = (await client.post(f"/api/conversations/{conv_id}/ai", json={"enabled": False}, headers=AUTH)).json()
    assert off["status"] == "human" and off["human_until"] is None
    on = (await client.post(f"/api/conversations/{conv_id}/ai", json={"enabled": True}, headers=AUTH)).json()
    assert on["status"] == "ai"
    msgs = (await client.get(f"/api/conversations/{conv_id}/messages", headers=AUTH)).json()
    assert [m["role"] for m in msgs] == ["customer", "ai"]
