"""LLM uchun suhbat tarixi: oxirgi N xabar to'liq, undan eskisi qisqa summary ko'rinishida."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.base import LLMClient
from app.ai.masking import PhoneMasker
from app.models import Conversation, Message

log = logging.getLogger(__name__)

HISTORY_ROLES = ("customer", "ai", "staff")
SUMMARY_PROMPT = (
    "Quyidagi do'kon va mijoz suhbatini 5 gapgacha qisqa xulosa qil: mijoz nimani qidirdi, nimalar taklif "
    "qilindi, kelishilgan narsalar, ochiq savollar. Telefon raqamlarni yozma. Faqat xulosani yoz."
)


async def load_history(session: AsyncSession, conv: Conversation, upto_id: int | None = None) -> list[Message]:
    stmt = select(Message).where(
        Message.conversation_id == conv.id,
        Message.role.in_(HISTORY_ROLES),
        Message.id > conv.summarized_upto_id,
    )
    if upto_id is not None:
        stmt = stmt.where(Message.id <= upto_id)
    return list(await session.scalars(stmt.order_by(Message.id)))


def _line(msg: Message, masker: PhoneMasker) -> tuple[str, str]:
    text = masker.mask(msg.content or "")
    if msg.role == "customer":
        return "user", text or "[bo'sh xabar]"
    if msg.role == "staff":
        return "assistant", f"(sotuvchi o'zi yozgan) {text}"
    return "assistant", text


def to_llm_messages(history: list[Message], masker: PhoneMasker, summary: str = "") -> list[dict]:
    """Rollar navbatma-navbat bo'lishi kerak: ketma-ket bir xil roldagi xabarlar birlashtiriladi."""
    turns: list[dict] = []
    for msg in history:
        role, text = _line(msg, masker)
        if not text.strip():
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"][0]["text"] += "\n" + text
        else:
            turns.append({"role": role, "content": [{"type": "text", "text": text}]})
    if summary:
        prefix = f"[Oldingi suhbat xulosasi: {summary}]"
        if turns and turns[0]["role"] == "user":
            turns[0]["content"][0]["text"] = prefix + "\n" + turns[0]["content"][0]["text"]
        else:
            turns.insert(0, {"role": "user", "content": [{"type": "text", "text": prefix}]})
    if turns and turns[0]["role"] == "assistant":
        turns.insert(0, {"role": "user", "content": [{"type": "text", "text": "(suhbat davomi)"}]})
    return turns


async def maybe_summarize(
    session: AsyncSession, conv: Conversation, history: list[Message], llm: LLMClient, keep: int, masker: PhoneMasker
) -> list[Message]:
    """Tarix 2*keep dan oshsa, eski qismini summary'ga aylantiradi. Xato bo'lsa tarix o'zgarmaydi."""
    if len(history) <= keep * 2:
        return history
    old, recent = history[:-keep], history[-keep:]
    transcript = "\n".join(f"{m.role}: {masker.mask(m.content or '')}" for m in old)
    if conv.summary:
        transcript = f"Avvalgi xulosa: {conv.summary}\n{transcript}"
    try:
        resp = await llm.chat(
            system=SUMMARY_PROMPT,
            messages=[{"role": "user", "content": [{"type": "text", "text": transcript}]}],
            max_tokens=400,
        )
    except Exception:
        log.warning("Summary yaratilmadi", exc_info=True)
        return history
    if resp.text:
        conv.summary = resp.text
        conv.summarized_upto_id = old[-1].id
        return recent
    return history
