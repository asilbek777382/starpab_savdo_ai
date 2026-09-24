from datetime import UTC, datetime

from redis.asyncio import Redis


async def customer_allowed(redis: Redis, shop_id: int, external_user_id: int, per_minute: int) -> bool:
    minute = datetime.now(UTC).strftime("%Y%m%d%H%M")
    key = f"rl:cust:{shop_id}:{external_user_id}:{minute}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 120)
    return count <= per_minute


def _day_key(shop_id: int) -> str:
    return f"tok:shop:{shop_id}:{datetime.now(UTC).strftime('%Y%m%d')}"


async def add_shop_tokens(redis: Redis, shop_id: int, tokens: int) -> int:
    key = _day_key(shop_id)
    total = await redis.incrby(key, tokens)
    await redis.expire(key, 2 * 24 * 3600)
    return total


async def shop_tokens_today(redis: Redis, shop_id: int) -> int:
    return int(await redis.get(_day_key(shop_id)) or 0)
