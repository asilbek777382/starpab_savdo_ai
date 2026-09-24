from redis.asyncio import Redis

DEDUP_TTL_SECONDS = 24 * 3600


async def is_duplicate_update(redis: Redis, update_id: int) -> bool:
    """Telegram bir update'ni qayta yuborishi mumkin: update_id 24 soat eslab qolinadi."""
    added = await redis.set(f"tg:update:{update_id}", 1, nx=True, ex=DEDUP_TTL_SECONDS)
    return not added
