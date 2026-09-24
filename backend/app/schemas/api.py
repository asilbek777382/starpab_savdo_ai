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
    telegram_user_id: int
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


class TestChatOut(BaseModel):
    status: str
    replies: list[dict]
    order_number: int | None
    lead_id: int | None = None
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
