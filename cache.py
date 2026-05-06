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

TAROT_NAMES_CACHE = None

async def get_tarot_names() -> dict:
    global TAROT_NAMES_CACHE
    if TAROT_NAMES_CACHE is not None:
        return TAROT_NAMES_CACHE

    from loguru import logger
    try:
        cached = await redis_client.get("system:tarot_names")
        if cached:
            try:
                TAROT_NAMES_CACHE = json.loads(cached)
                return TAROT_NAMES_CACHE
            except Exception as e:
                logger.error(f"Ошибка декодирования имен таро из кэша: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка получения имен таро из кэша: {str(e)}")

    try:
        async with aiofiles.open("tarot_ids.json", "r", encoding="utf-8") as f:
            content = await f.read()
            names = json.loads(content)
            TAROT_NAMES_CACHE = names
            try:
                await redis_client.set("system:tarot_names", json.dumps(names, ensure_ascii=False))
            except Exception as e:
                logger.error(f"Ошибка сохранения имен таро в кэш: {str(e)}")
            return names
    except Exception as e:
        logger.error(f"Ошибка загрузки имен таро из файла: {str(e)}")
        return {}
