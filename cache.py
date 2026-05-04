import os
import json
from upstash_redis.asyncio import Redis

redis_client = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL", ""),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
)

async def acquire_lock(vk_id: int, ttl: int = 90) -> bool:
    res = await redis_client.set(f"lock:{vk_id}", "1", nx=True, ex=ttl)
    return bool(res)

async def release_lock(vk_id: int):
    await redis_client.delete(f"lock:{vk_id}")

async def set_fsm_state(vk_id: int, state_data: str, ttl: int = 86400):
    if not state_data:
        await redis_client.delete(f"fsm:{vk_id}")
    else:
        await redis_client.set(f"fsm:{vk_id}", state_data, ex=ttl)

async def get_fsm_state(vk_id: int):
    return await redis_client.get(f"fsm:{vk_id}")

TAROT_NAMES_CACHE = None

async def get_tarot_names() -> dict:
    global TAROT_NAMES_CACHE
    if TAROT_NAMES_CACHE is not None:
        return TAROT_NAMES_CACHE

    # Try fetching from Redis first
    try:
        cached = await redis_client.get("system:tarot_names")
        if cached:
            try:
                TAROT_NAMES_CACHE = json.loads(cached)
                return TAROT_NAMES_CACHE
            except Exception:
                pass
    except Exception:
        pass # Ignore redis connection errors if UPSTASH URL is missing in dev

    # Load from file if not in Redis
    try:
        with open("tarot_ids.json", "r", encoding="utf-8") as f:
            names = json.load(f)
            TAROT_NAMES_CACHE = names
            try:
                await redis_client.set("system:tarot_names", json.dumps(names, ensure_ascii=False))
            except Exception:
                pass
            return names
    except Exception:
        return {}
