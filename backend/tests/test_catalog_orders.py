import pytest
from sqlalchemy import select

from app.models import Order, ProductVariant, ShopSettings
from app.services import cart as cart_svc
from app.services.catalog_import import import_catalog, template_xlsx
from app.services.orders import OrderError, create_order, set_order_status
from app.services.search import search_products
from tests.factories import make_business_channel, make_catalog, make_conversation, make_shop


@pytest.fixture
async def shop_data(session):
    shop = await make_shop(session)
    products = await make_catalog(session, shop.id)
    channel = await make_business_channel(session, shop.id)
    customer, conv = await make_conversation(session, channel)
    await session.commit()
    return {"shop": shop, **products, "channel": channel, "customer": customer, "conv": conv}


async def test_search_across_scripts_and_typos(session, shop_data):
    shop_id = shop_data["shop"].id
    for query in ("qora ko'ylak", "Қора кўйлак", "koylak", "qora koylek"):
        result = await search_products(session, shop_id, query)
        assert result["products"], query
        assert result["products"][0]["name"] == "Qora ko'ylak", query


async def test_search_filters_size_and_reports_alternatives(session, shop_data):
    shop_id = shop_data["shop"].id
    found = await search_products(session, shop_id, "ko'ylak", size="42")
    variants = found["products"][0]["variants"]
    assert [v["attrs"]["size"] for v in variants] == ["42"] and variants[0]["in_stock"]

    missing = await search_products(session, shop_id, "ko'ylak", size="50")
    assert missing["products"] == [] and missing["alternatives"]

    cheap = await search_products(session, shop_id, "sumka", max_price=100_000)
    assert cheap["products"] == []


async def test_search_is_scoped_to_shop(session, shop_data):
    other = await make_shop(session, "Boshqa do'kon")
    await session.commit()
    assert (await search_products(session, other.id, "qora ko'ylak"))["products"] == []


async def test_cart_uses_db_prices_and_stock(session, shop_data):
    conv, dress = shop_data["conv"], shop_data["dress"]
    v42, v44 = dress.variants
    view = await cart_svc.update_cart(session, conv, "add", v42.id, 2)
    assert view["subtotal"] == 500_000 and conv.stage == "cart"
    with pytest.raises(cart_svc.CartError):
        await cart_svc.update_cart(session, conv, "add", v42.id, 2)  # jami 4 > qoldiq 3
    with pytest.raises(cart_svc.CartError):
        await cart_svc.update_cart(session, conv, "add", v44.id, 1)  # qoldiq 0
    view = await cart_svc.update_cart(session, conv, "set", v42.id, 1)
    assert view["items"][0]["qty"] == 1
    view = await cart_svc.update_cart(session, conv, "remove", v42.id)
    assert view["items"] == []


async def test_cart_rejects_other_shop_variant(session, shop_data):
    other = await make_shop(session, "Boshqa")
    products = await make_catalog(session, other.id)
    with pytest.raises(cart_svc.CartError):
        await cart_svc.update_cart(session, shop_data["conv"], "add", products["bag"].variants[0].id, 1)


async def test_create_order_computes_totals_and_reserves_stock(session, shop_data):
    conv, dress, bag = shop_data["conv"], shop_data["dress"], shop_data["bag"]
    await cart_svc.update_cart(session, conv, "add", dress.variants[0].id, 2)
    await cart_svc.update_cart(session, conv, "add", bag.variants[0].id, 1)
    shop_settings = await session.get(ShopSettings, shop_data["shop"].id)
    order = await create_order(
        session,
        conv=conv,
        customer=shop_data["customer"],
        settings=shop_settings,
        name="Aziza",
        phone="+998901234567",
        address="Chilonzor 9",
    )
    assert order.number == 1
    assert order.subtotal == 2 * 250_000 + 180_000
    assert order.delivery_fee == 20_000 and order.total == order.subtotal + 20_000
    assert conv.cart == [] and conv.stage == "order_created"
    stock = await session.scalar(select(ProductVariant.stock).where(ProductVariant.id == dress.variants[0].id))
    assert stock == 1

    await set_order_status(session, order, "cancelled")
    stock = await session.scalar(select(ProductVariant.stock).where(ProductVariant.id == dress.variants[0].id))
    assert stock == 3

    with pytest.raises(OrderError):
        await create_order(
            session,
            conv=conv,
            customer=shop_data["customer"],
            settings=shop_settings,
            name="A",
            phone="+1",
            address="x",
        )


async def test_order_numbers_are_sequential_per_shop(session, shop_data):
    shop_settings = await session.get(ShopSettings, shop_data["shop"].id)
    numbers = []
    for _ in range(2):
        await cart_svc.update_cart(session, shop_data["conv"], "add", shop_data["bag"].variants[0].id, 1)
        order = await create_order(
            session,
            conv=shop_data["conv"],
            customer=shop_data["customer"],
            settings=shop_settings,
            name="A",
            phone="+998901234567",
            address="Nukus",
        )
        numbers.append(order.number)
    assert numbers == [1, 2]
    assert "hududi aniqlanmadi" in order.comment and order.delivery_fee == 0
    assert await session.scalar(select(Order.id).where(Order.number == 2))


async def test_import_catalog_from_xlsx_template(session, shop_data):
    shop_id = shop_data["shop"].id
    result = await import_catalog(session, shop_id, template_xlsx(), "katalog.xlsx")
    assert result.errors == []
    assert result.updated == 1 and result.created == 0  # "Qora ko'ylak" allaqachon bor
    found = await search_products(session, shop_id, "qora ko'ylak", size="46")
    assert found["products"][0]["variants"][0]["stock"] == 1

    csv = b"nomi;narx;razmer\nOq futbolka;90000;M,L\n"
    result = await import_catalog(session, shop_id, csv, "k.csv")
    assert result.created == 1
    found = await search_products(session, shop_id, "futbolka", size="L")
    assert found["products"][0]["price"] == 90_000
