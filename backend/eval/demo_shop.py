"""Eval uchun demo do'kon: ayollar kiyimi."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ShopSettings
from app.services.catalog import save_product
from app.services.shops import create_shop

CATALOG = [
    {
        "name": "Qora ko'ylak",
        "price": 250_000,
        "description": "Paxtali yozgi ko'ylak, tizzagacha",
        "category": "Ko'ylaklar",
        "variants": [
            {"attrs": {"size": "42", "color": "qora"}, "stock": 3},
            {"attrs": {"size": "44", "color": "qora"}, "stock": 0},
            {"attrs": {"size": "46", "color": "qora"}, "stock": 2},
        ],
        "images": ["https://picsum.photos/seed/dress/600/800"],
    },
    {
        "name": "Charm sumka",
        "price": 180_000,
        "description": "Tabiiy charm, yelkaga osiladigan",
        "category": "Sumkalar",
        "variants": [{"attrs": {"color": "jigarrang"}, "stock": 5}, {"attrs": {"color": "qora"}, "stock": 1}],
        "images": [],
    },
    {
        "name": "Oq krossovka",
        "price": 320_000,
        "description": "Yengil, kundalik",
        "category": "Oyoq kiyim",
        "variants": [{"attrs": {"size": s, "color": "oq"}, "stock": 2} for s in ("37", "38", "39", "40")],
        "images": [],
    },
]


async def create_demo_shop(session: AsyncSession, owner_id: int = 1):
    shop = await create_shop(session, owner_id, "Eval", "Dilnoza Style")
    settings = await session.get(ShopSettings, shop.id)
    settings.faq_text = "Ayollar kiyimi do'koni. Qaytarish 3 kun ichida, yorlig'i bilan."
    settings.address = "Toshkent, Chilonzor tumani, Bunyodkor ko'chasi 5"
    settings.working_hours = "Har kuni 10:00–21:00"
    settings.payment_methods = "Naqd, Click, Payme"
    settings.rules_text = "Chegirma bermaymiz. Samarqandga faqat pochta orqali."
    settings.delivery_zones = [
        {"name": "Toshkent shahri", "keywords": ["toshkent", "chilonzor", "yunusobod"], "fee": 20000, "eta": "1 kun"},
        {"name": "Viloyatlar (pochta)", "keywords": ["samarqand", "buxoro", "andijon"], "fee": 40000, "eta": "3 kun"},
    ]
    for item in CATALOG:
        await save_product(
            session,
            shop.id,
            product=None,
            name=item["name"],
            price=item["price"],
            description=item["description"],
            category_name=item["category"],
            variants=item["variants"],
            images=item["images"],
        )
    await session.flush()
    return shop
