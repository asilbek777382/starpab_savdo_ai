"""Bitta AI javobi (turn): tarix → LLM → toollar → ... → yakuniy matn."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select

from app.ai.context import load_history, maybe_summarize, to_llm_messages
from app.ai.llm.base import LLMClient, LLMError, Usage
from app.ai.prompt import build_state_note, build_system_prompt, fmt_sum
from app.ai.tools import execute_tool, tools_for_mode
from app.ai.turn import TurnContext
from app.config import get_settings
from app.models import Message, Product
from app.services.cart import cart_view
from app.services.handoff import handoff_reply_for

log = logging.getLogger(__name__)

FALLBACK_TEXT = "Xabaringiz qabul qilindi, tez orada javob beramiz."


@dataclass
class TurnResult:
    text: str
    usage: Usage
    cost: Decimal
    llm_failed: bool = False


def cost_uzs(usage: Usage) -> Decimal:
    s = get_settings()
    usd = (
        usage.input_tokens * s.llm_price_in
        + usage.cache_write_tokens * s.llm_price_in * 1.25
        + usage.cache_read_tokens * s.llm_price_in * 0.1
        + usage.output_tokens * s.llm_price_out
    ) / 1_000_000
    return Decimal(str(round(usd * s.usd_to_uzs, 2)))


async def catalog_lines(ctx: TurnContext) -> list[str] | None:
    """Katalog kichik bo'lsa, nom va narxlar ro'yxati promptga qo'shiladi."""
    s = get_settings()
    count = await ctx.session.scalar(
        select(func.count()).select_from(Product).where(Product.shop_id == ctx.shop.id, Product.is_active)
    )
    if not count or count > s.small_catalog_threshold:
        return None
    rows = await ctx.session.execute(
        select(Product.id, Product.name, Product.price)
        .where(Product.shop_id == ctx.shop.id, Product.is_active)
        .order_by(Product.id)
    )
    return [f"- {r.name} — {fmt_sum(r.price)} (id {r.id})" for r in rows]


async def run_turn(ctx: TurnContext, llm: LLMClient, upto_id: int | None = None) -> TurnResult:
    s = get_settings()
    history = await load_history(ctx.session, ctx.conv, upto_id)
    history = await maybe_summarize(ctx.session, ctx.conv, history, llm, s.history_full_messages, ctx.masker)
    messages = to_llm_messages(history[-s.history_full_messages * 2 :], ctx.masker, ctx.conv.summary)
    if not messages or messages[-1]["role"] != "user":
        return TurnResult(text="", usage=Usage(), cost=Decimal(0))

    state = build_state_note(
        ctx.conv.stage, await cart_view(ctx.session, ctx.conv), ctx.customer.name, ctx.conv.contact or {}
    )
    messages[-1]["content"].append({"type": "text", "text": state})
    system = build_system_prompt(ctx.shop, ctx.settings, await catalog_lines(ctx))

    tools = tools_for_mode(ctx.settings.ai_mode)
    usage = Usage()
    text = ""
    try:
        for _ in range(s.llm_max_tool_iterations):
            resp = await llm.chat(system=system, messages=messages, tools=tools)
            usage += resp.usage
            if resp.stop_reason != "tool_use" or not resp.tool_calls:
                text = resp.text
                break
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for call in resp.tool_calls:
                content, is_error = await execute_tool(ctx, call.name, call.input)
                results.append(
                    {"type": "tool_result", "tool_use_id": call.id, "content": content, "is_error": is_error}
                )
                ctx.session.add(
                    Message(
                        shop_id=ctx.shop.id,
                        conversation_id=ctx.conv.id,
                        role="tool",
                        content=f"{call.name}({call.input}) -> {content[:2000]}",
                        answered=True,
                    )
                )
            messages.append({"role": "user", "content": results})
        else:
            log.warning("Tool iteratsiyalari limiti tugadi (conv=%s)", ctx.conv.id)
    except LLMError:
        # Provayder ishlamasa yoki so'rov rad etilsa (masalan, kalit noto'g'ri) — mijoz javobsiz qolmaydi
        log.exception("LLM ishlamadi (conv=%s)", ctx.conv.id)
        return TurnResult(text=FALLBACK_TEXT, usage=usage, cost=cost_uzs(usage), llm_failed=True)

    if not text and ctx.handed_off:
        text = handoff_reply_for(history[-1].content if history else "")
    if not text and ctx.order is not None:
        text = f"Buyurtmangiz #{ctx.order.number} qabul qilindi. Jami: {fmt_sum(ctx.order.total)}."
    if not text:
        text = FALLBACK_TEXT
    return TurnResult(text=_unmask_for_customer(text, ctx), usage=usage, cost=cost_uzs(usage))


def _unmask_for_customer(text: str, ctx: TurnContext) -> str:
    """LLM javobida [PHONE_1] qolgan bo'lsa, mijozga asl raqamni ko'rsatamiz."""
    for token, phone in ctx.masker.phones.items():
        text = text.replace(token, phone)
    return text
