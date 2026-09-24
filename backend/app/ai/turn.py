from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.masking import PhoneMasker
from app.models import Channel, Conversation, Customer, Order, Shop, ShopSettings
from app.services.embeddings import EmbeddingProvider
from app.telegram.outbound import Outbound


class Notifier(Protocol):
    async def new_order(self, order: Order, customer: Customer, channel: Channel) -> None: ...

    async def handoff(self, conv: Conversation, customer: Customer, reason: str) -> None: ...

    async def flush(self) -> None: ...


class NullNotifier:
    async def new_order(self, order: Order, customer: Customer, channel: Channel) -> None:
        return None

    async def handoff(self, conv: Conversation, customer: Customer, reason: str) -> None:
        return None

    async def flush(self) -> None:
        return None


@dataclass
class TurnContext:
    session: AsyncSession
    shop: Shop
    settings: ShopSettings
    conv: Conversation
    customer: Customer
    channel: Channel
    outbound: Outbound
    notifier: Notifier
    masker: PhoneMasker
    embedder: EmbeddingProvider | None = None
    order_source: str = "ai"
    # Turn natijalari
    handed_off: bool = False
    order: Order | None = None
    tool_log: list[dict] = field(default_factory=list)
