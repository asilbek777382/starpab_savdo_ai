"""Test ma'lumotlari: do'kon, katalog, mijoz."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Conversation, Customer, ShopSettings
from app.services.catalog import save_product
from app.services.shops import create_shop

OWNER_ID = 777
CUSTOMER_ID = 5555
BOT_TOKEN = "123456:TEST-TOKEN"

ZONES = [
    {"name": "Toshkent shahri", "keywords": ["toshkent", "chilonzor", "yunusobod"], "fee": 20000, "eta": "1 kun"},
    {"name": "Viloyatlar", "keywords": ["samarqand", "buxoro"], "fee": 40000, "eta": "3 kun"},
]


async def make_shop(session: AsyncSession, name: str = "Dilnoza Style"):
    shop = await create_shop(session, OWNER_ID, "Dilnoza", name)
    settings = await session.get(ShopSettings, shop.id)
    settings.delivery_zones = ZONES
    settings.faq_text = "Ayollar kiyimi do'koni."
    settings.payment_methods = "Naqd, Click, Payme"
    await session.flush()
    return shop


async def make_catalog(session: AsyncSession, shop_id: int) -> dict:
    dress = await save_product(
        session,
        shop_id,
        product=None,
        name="Qora ko'ylak",
        price=250_000,
        description="Paxtali yozgi ko'ylak",
        category_name="Ko'ylaklar",
        variants=[
            {"attrs": {"size": "42", "color": "qora"}, "stock": 3},
            {"attrs": {"size": "44", "color": "qora"}, "stock": 0},
        ],
        images=["https://example.com/dress1.jpg", "https://example.com/dress2.jpg"],
    )
    bag = await save_product(
        session,
        shop_id,
        product=None,
        name="Charm sumka",
        price=180_000,
        category_name="Sumkalar",
        variants=[{"attrs": {"color": "jigarrang"}, "stock": None}],
    )
    await session.flush()
    return {"dress": dress, "bag": bag}


async def make_business_channel(session: AsyncSession, shop_id: int, bcid: str = "bc-1") -> Channel:
    channel = Channel(
        shop_id=shop_id,
        type="tg_business",
        business_connection_id=bcid,
        owner_user_id=OWNER_ID,
        can_reply=True,
        is_enabled=True,
    )
    session.add(channel)
    await session.flush()
    return channel


async def make_conversation(session: AsyncSession, channel: Channel) -> tuple[Customer, Conversation]:
    customer = Customer(
        shop_id=channel.shop_id, channel_id=channel.id, external_user_id=CUSTOMER_ID, chat_id=CUSTOMER_ID, name="Aziza"
    )
    session.add(customer)
    await session.flush()
    conv = Conversation(shop_id=channel.shop_id, customer_id=customer.id, channel_id=channel.id, cart=[], contact={})
    session.add(conv)
    await session.flush()
    return customer, conv


def init_data(user_id: int = OWNER_ID, token: str = BOT_TOKEN, auth_date: int | None = None) -> str:
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAH",
        "user": json.dumps({"id": user_id, "first_name": "Dilnoza"}),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)
