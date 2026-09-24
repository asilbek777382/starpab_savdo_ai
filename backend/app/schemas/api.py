from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ShopOut(ORM):
    id: int
    name: str
    type: str
    language_default: str
    status: str
    plan: str
    trial_ends_at: datetime | None


class ShopUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = None
    language_default: str | None = None


class MeOut(BaseModel):
    telegram_user_id: int | None
    role: str
    shop: ShopOut
    bot_link: str


class DeliveryZone(BaseModel):
    name: str
    keywords: list[str] = []
    fee: int = Field(ge=0)
    eta: str | None = None
    center: tuple[float, float] | None = None
    radius_km: float | None = Field(default=None, gt=0)


class HandoffRules(BaseModel):
    silence_minutes: int = Field(default=30, ge=1, le=24 * 60)
    handoff_hours: float = Field(default=2, gt=0, le=72)
    allow_discounts: bool = False
    keywords: list[str] = []


class SettingsIO(ORM):
    faq_text: str = ""
    rules_text: str = ""
    address: str = ""
    delivery_zones: list[DeliveryZone] = []
    payment_methods: str = ""
    working_hours: str = ""
    tone: str = "friendly"
    handoff_rules: HandoffRules = HandoffRules()
    ai_enabled: bool = True
    ai_mode: Literal["sell", "lead"] = "sell"
    ai_tasks: str = Field(default="", max_length=4000)
    lead_chat_id: int | None = None
    handoff_after_lead: bool = True
    voice_mode: Literal["off", "on_voice", "always"] = "off"
    voice_gender: Literal["female", "male"] = "female"
    # Faqat o'qish uchun: serverda TTS (Azure) sozlanganmi
    voice_available: bool = False


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None


class CategoryOut(ORM):
    id: int
    name: str
    parent_id: int | None


class VariantIO(ORM):
    id: int | None = None
    sku: str | None = None
    attrs: dict[str, str] = {}
    price_override: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)


class ImageOut(ORM):
    id: int
    url: str


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    price: int = Field(ge=0)
    category_id: int | None = None
    category_name: str | None = None
    is_active: bool = True
    variants: list[VariantIO] = []
    images: list[HttpUrl] | None = None


class ProductOut(ORM):
    id: int
    name: str
    description: str
    price: int
    currency: str
    category_id: int | None
    is_active: bool
    variants: list[VariantIO]
    images: list[ImageOut]


class ImportOut(BaseModel):
    created: int
    updated: int
    errors: list[str]


class OrderOut(ORM):
    id: int
    number: int
    status: str
    items: list[dict]
    subtotal: int
    delivery_fee: int
    total: int
    customer_name: str | None
    phone: str | None
    address: str | None
    location: dict | None
    comment: str | None
    source: str
    created_at: datetime


class OrderStatusIn(BaseModel):
    status: str


class ConversationOut(ORM):
    id: int
    customer_id: int
    customer_name: str | None = None
    channel_type: str | None = None
    status: str
    stage: str
    human_until: datetime | None
    last_message_at: datetime | None


class MessageOut(ORM):
    id: int
    role: str
    content: str
    created_at: datetime
    tokens_in: int
    tokens_out: int
    cost: Decimal


class AIToggleIn(BaseModel):
    enabled: bool
    minutes: int | None = Field(default=None, ge=1, le=7 * 24 * 60)


class TestChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    reset: bool = False
    # Mijoz ovozli xabar yuborgandek sinash ("mijoz ovozli yozsa" rejimi uchun)
    as_voice: bool = False


class TestChatOut(BaseModel):
    status: str
    replies: list[dict]
    order_number: int | None
    lead_id: int | None = None
    voice: bool = False
    handed_off: bool
    tools: list[dict]


class LeadOut(ORM):
    id: int
    customer_id: int
    conversation_id: int | None
    channel_type: str
    name: str | None
    phone: str
    interest: str
    note: str | None
    status: str
    created_at: datetime


class LeadStatusIn(BaseModel):
    status: Literal["new", "contacted", "won", "lost"]


class StatsOut(BaseModel):
    days: int
    conversations: int
    orders: int
    conversion: float
    ai_orders_revenue: int
    handoffs: int
    leads: int
    ai_cost: Decimal
    month_conversations: int
    month_limit: int


# ---------- auth ----------


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=1, max_length=200)
    shop_name: str = Field(min_length=1, max_length=200)
    lang: Literal["uz", "ru"] = "uz"


class LoginIn(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=1, max_length=200)


class MagicIn(BaseModel):
    token: str = Field(min_length=10, max_length=100)


class PasswordIn(BaseModel):
    old_password: str | None = None
    new_password: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=30)  # magic link bilan kirganlar uchun


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    lang: Literal["uz", "ru"] | None = None


class ShopBrief(BaseModel):
    id: int
    name: str
    role: str
    plan: str
    status: str


class AccountOut(BaseModel):
    id: int
    name: str
    phone: str | None
    lang: str
    telegram_linked: bool
    has_password: bool
    is_platform_admin: bool
    shops: list[ShopBrief]


class LinkOut(BaseModel):
    url: str
    expires_in: int


class ChannelOut(ORM):
    id: int
    type: str
    can_reply: bool
    is_enabled: bool
    display_name: str | None = None
    token_expires_at: datetime | None = None


class ChannelsOut(BaseModel):
    channels: list[ChannelOut]
    bot_username: str
    bot_link: str
    business_connected: bool
    instagram_configured: bool = False
    instagram_allowed: bool = False
    instagram: ChannelOut | None = None


class DailyPoint(BaseModel):
    date: str
    conversations: int
    orders: int
    leads: int


# ---------- platforma admini ----------


class AdminShopRow(BaseModel):
    id: int
    name: str
    owner_name: str | None
    owner_phone: str | None
    plan: str
    status: str
    trial_ends_at: datetime | None
    paid_until: datetime | None
    month_conversations: int
    month_cost: Decimal
    orders_30d: int
    leads_30d: int
    business_connected: bool
    instagram_connected: bool = False
    created_at: datetime


class AdminOverview(BaseModel):
    shops: int
    trials_active: int
    paying: int
    mrr: int
    month_conversations: int
    month_ai_cost: Decimal
    month_revenue: int


class AdminPlanIn(BaseModel):
    plan: Literal["trial", "start", "business", "pro"] | None = None
    trial_days: int | None = Field(default=None, ge=1, le=365)
    extra_conversations: int | None = Field(default=None, ge=0, le=100_000)


class AdminStatusIn(BaseModel):
    status: Literal["active", "paused"]


class AdminPaymentIn(BaseModel):
    plan: Literal["start", "business", "pro"]
    months: int = Field(default=1, ge=1, le=24)
    amount: int = Field(ge=0)
    provider: Literal["manual", "click", "payme", "card"] = "manual"
    note: str | None = Field(default=None, max_length=300)


class PaymentOut(ORM):
    id: int
    amount: int
    provider: str
    provider_txn_id: str | None
    status: str
    created_at: datetime


class AdminShopDetail(BaseModel):
    shop: AdminShopRow
    payments: list[PaymentOut]
    channels: list[ChannelOut]
