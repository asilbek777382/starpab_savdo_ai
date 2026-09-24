"""AI sifatini o'lchash: eval/cases.jsonl dagi holatlarni haqiqiy LLM bilan o'tkazadi.

Ishga tushirish (backend/ ichida):
    EVAL_DATABASE_URL=postgresql+asyncpg://aiop:aiop@localhost:5432/aiop_eval \
    ANTHROPIC_API_KEY=... uv run python -m eval.run_eval [--only id1,id2] [--min 0.85]

--dry-run: LLM o'rniga soxta javob (faqat skript ishlashini tekshirish uchun).
Har bir prompt yoki model o'zgarishidan keyin ishga tushiring; natija eval/results/ ga yoziladi.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import db
from app.ai.llm.base import LLMResponse, Usage
from app.ai.llm.factory import build_llm
from app.config import get_settings
from app.db import Base
from app.models import Channel, Conversation, Customer, Message, ShopSettings
from app.runtime import Runtime
from app.services.conversation import reply_to_conversation
from app.services.handoff import detect_script
from app.telegram.outbound import RecordingOutbound
from eval.demo_shop import create_demo_shop

HERE = Path(__file__).parent


class DryLLM:
    async def chat(self, **kwargs) -> LLMResponse:
        return LLMResponse(content=[{"type": "text", "text": "Salom"}], stop_reason="end_turn", usage=Usage())


def check(case: dict, replies: list[str], tools: list[dict], handed_off: bool, order: bool, lead: bool) -> list[str]:
    exp, errors = case["expect"], []
    called = {t["tool"] for t in tools}
    final = replies[-1] if replies else ""
    if exp.get("tools_any") and not called & set(exp["tools_any"]):
        errors.append(f"toollardan biri chaqirilmadi: {exp['tools_any']} (chaqirilgan: {sorted(called)})")
    if exp.get("tools_none") and called & set(exp["tools_none"]):
        errors.append(f"taqiqlangan tool chaqirildi: {sorted(called & set(exp['tools_none']))}")
    if "product" in exp:
        names = {
            p["name"]
            for t in tools
            if t["tool"] == "search_products"
            for p in (t["result"].get("products", []) + t["result"].get("alternatives", []))
        }
        if exp["product"] not in names:
            errors.append(f"mahsulot topilmadi: {exp['product']} (topilgan: {sorted(names)})")
    if "handoff" in exp and exp["handoff"] != handed_off:
        errors.append(f"handoff kutilgan={exp['handoff']}, bo'ldi={handed_off}")
    if "order" in exp and exp["order"] != order:
        errors.append(f"buyurtma kutilgan={exp['order']}, bo'ldi={order}")
    if "lead" in exp and exp["lead"] != lead:
        errors.append(f"lid kutilgan={exp['lead']}, bo'ldi={lead}")
    if exp.get("contains_any") and not any(s.lower() in " ".join(replies).lower() for s in exp["contains_any"]):
        errors.append(f"javobda yo'q: {exp['contains_any']}")
    if exp.get("not_contains") and any(s in " ".join(replies) for s in exp["not_contains"]):
        errors.append(f"javobda bo'lmasligi kerak edi: {exp['not_contains']}")
    if exp.get("script") and final and detect_script(final) != exp["script"]:
        errors.append(f"til/yozuv: kutilgan {exp['script']}, bo'ldi {detect_script(final)}")
    return errors


async def run_case(rt: Runtime, shop_id: int, channel_id: int, case: dict, n: int) -> dict:
    async with db.get_sessionmaker()() as session:
        settings = await session.get(ShopSettings, shop_id)
        settings.ai_mode = case.get("mode", "sell")
        customer = Customer(shop_id=shop_id, channel_id=channel_id, external_user_id=10_000 + n, chat_id=10_000 + n)
        session.add(customer)
        await session.flush()
        conv = Conversation(shop_id=shop_id, customer_id=customer.id, channel_id=channel_id, cart=[], contact={})
        session.add(conv)
        await session.commit()

        replies, tools, handed_off, order, lead, cost = [], [], False, False, False, 0.0
        started = time.monotonic()
        for text_ in case["messages"]:
            session.add(Message(shop_id=shop_id, conversation_id=conv.id, role="customer", content=text_))
            await session.commit()
            outbound = RecordingOutbound()
            result = await reply_to_conversation(session, rt, conv.id, outbound=outbound, check_billing=False)
            replies += [s["text"] for s in outbound.sent if s["type"] == "text"]
            tools += result.tools
            handed_off |= result.handed_off
            order |= result.order_number is not None
            lead |= result.lead_id is not None
        cost_row = await session.execute(
            text("SELECT coalesce(sum(cost), 0) FROM messages WHERE conversation_id = :c"), {"c": conv.id}
        )
        cost = float(cost_row.scalar() or 0)
    errors = check(case, replies, tools, handed_off, order, lead)
    return {
        "id": case["id"],
        "ok": not errors,
        "errors": errors,
        "replies": replies,
        "tools": [t["tool"] for t in tools],
        "cost_uzs": round(cost, 2),
        "seconds": round(time.monotonic() - started, 1),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--min", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s = get_settings()
    url = os.environ.get("EVAL_DATABASE_URL", s.database_url.rsplit("/", 1)[0] + "/aiop_eval")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    db.set_engine(engine)

    llm = DryLLM() if args.dry_run else build_llm()
    rt = Runtime(redis=Redis.from_url(s.redis_url, decode_responses=True), llm=llm)
    async with db.get_sessionmaker()() as session:
        shop = await create_demo_shop(session)
        channel = Channel(shop_id=shop.id, type="test", can_reply=True, is_enabled=True)
        session.add(channel)
        await session.commit()
        shop_id, channel_id = shop.id, channel.id

    cases = [json.loads(line) for line in (HERE / "cases.jsonl").read_text().splitlines() if line.strip()]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    results = []
    for n, case in enumerate(cases):
        res = await run_case(rt, shop_id, channel_id, case, n)
        results.append(res)
        mark = "✅" if res["ok"] else "❌"
        print(f"{mark} {res['id']:<28} {res['seconds']:>5}s {res['cost_uzs']:>8} so'm  {'; '.join(res['errors'])}")

    passed = sum(r["ok"] for r in results)
    score = passed / len(results) if results else 0.0
    total_cost = sum(r["cost_uzs"] for r in results)
    print(f"\nNatija: {passed}/{len(results)} ({score:.0%}), jami xarajat ≈ {total_cost:.0f} so'm")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{s.llm_model}.json"
    out.write_text(json.dumps({"model": s.llm_model, "score": score, "results": results}, ensure_ascii=False, indent=2))
    print(f"Batafsil: {out}")
    await rt.redis.aclose()
    await engine.dispose()
    return 0 if score >= args.min else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
