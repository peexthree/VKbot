import os
import json
import aiofiles
from upstash_redis.asyncio import Redis

redis_client = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL", ""),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
)

async def acquire_lock(vk_id: int | str, ttl: int = 90) -> bool:
    res = await redis_client.set(f"lock:{vk_id}", "1", nx=True, ex=ttl)
    return bool(res)

async def release_lock(vk_id: int | str):
    await redis_client.delete(f"lock:{vk_id}")

async def check_throttle(vk_id: int | str) -> bool:
    """Returns True if the user is throttled (should be ignored), False otherwise."""
    from loguru import logger
    try:
        res = await redis_client.set(f"throttle:{vk_id}", "1", nx=True, ex=2)
        return not bool(res)
    except Exception as e:
        logger.error(f"Ошибка проверки троттлинга для {vk_id}: {str(e)}")
        return False

async def check_and_set_throttle_warning(vk_id: int | str) -> bool:
    """Returns True if a warning should be sent (i.e. cooldown is over), False if warning is on cooldown."""
    from loguru import logger
    try:
        res = await redis_client.set(f"throttle_warning:{vk_id}", "1", nx=True, ex=10)
        return bool(res)
    except Exception as e:
        logger.error(f"Ошибка проверки предупреждения троттлинга для {vk_id}: {str(e)}")
        return False

async def set_fsm_state(vk_id: int | str, state_data: str, ttl: int = 86400):
    if not state_data:
        await redis_client.delete(f"fsm:{vk_id}")
    else:
        await redis_client.set(f"fsm:{vk_id}", state_data, ex=ttl)

async def get_fsm_state(vk_id: int | str):
    return await redis_client.get(f"fsm:{vk_id}")

TAROT_NAMES_CACHE = {}

def load_tarot_names_sync():
    global TAROT_NAMES_CACHE
    from loguru import logger
    try:
        with open("tarot_ids.json", "r", encoding="utf-8") as f:
            TAROT_NAMES_CACHE = json.load(f)
            logger.info("Tarot names loaded into global cache successfully.")
    except Exception as e:
        logger.error(f"Ошибка загрузки имен таро из файла: {str(e)}")
        TAROT_NAMES_CACHE = {}

async def get_tarot_names() -> dict:
    global TAROT_NAMES_CACHE
    if not TAROT_NAMES_CACHE:
        load_tarot_names_sync()
    return TAROT_NAMES_CACHE
