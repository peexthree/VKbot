import json
import os

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
        # Reduced throttle from 2s to 0.8s for better UX
        res = await redis_client.set(f"throttle:{vk_id}", "1", nx=True, px=800)
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

async def set_temp_birth_data(vk_id: int | str, data: dict, ttl: int = 86400):
    """Сохраняет данные рождения в Redis на 24 часа"""
    await redis_client.set(f"user:birth_data:{vk_id}", json.dumps(data, ensure_ascii=False), ex=ttl)

async def get_temp_birth_data(vk_id: int | str) -> dict | None:
    """Получает данные рождения из Redis на 24 часа (строгий TTL)"""
    res = await redis_client.get(f"user:birth_data:{vk_id}")
    if res:
        try:
            return json.loads(res)
        except Exception:
            pass
    return None

async def get_core_profile(vk_id: int | str) -> str:
    """Получает core_profile из Redis"""
    res = await redis_client.get(f"user:core_profile:{vk_id}")
    return res.decode() if isinstance(res, bytes) else (res or "")

async def add_reading_to_history(vk_id: int | str, item: dict, ttl: int = 86400):
    """Добавляет разбор в историю в Redis на 24 часа"""
    history = await get_readings_history(vk_id)
    history.append(item)
    await redis_client.set(f"user:readings_history:{vk_id}", json.dumps(history, ensure_ascii=False), ex=ttl)

async def get_readings_history(vk_id: int | str) -> list:
    """Получает историю разборов из Redis, при отсутствии кэша загружает из БД"""
    res = await redis_client.get(f"user:readings_history:{vk_id}")
    if res:
        try:
            return json.loads(res)
        except Exception:
            pass

    # Фолбэк на Supabase
    try:
        from database import get_user
        user = await get_user(int(vk_id))
        if user:
            history = user.get("readings_history") or []
            if not isinstance(history, list):
                history = []
            # Кэшируем в Redis на 24 часа (86400 секунд)
            await redis_client.set(f"user:readings_history:{vk_id}", json.dumps(history, ensure_ascii=False), ex=86400)
            return history
    except Exception as e:
        from loguru import logger
        logger.error(f"Ошибка получения истории из Supabase для {vk_id}: {e}")
    return []

async def set_destiny_card_data(vk_id: int | str, data: dict, ttl: int = 86400):
    """Сохраняет данные карты судьбы в Redis на 24 часа"""
    await redis_client.set(f"user:destiny_card:{vk_id}", json.dumps(data, ensure_ascii=False), ex=ttl)

async def get_destiny_card_data(vk_id: int | str) -> dict | None:
    """Получает данные карты судьбы из Redis"""
    res = await redis_client.get(f"user:destiny_card:{vk_id}")
    if res:
        try:
            return json.loads(res)
        except Exception:
            pass
    return None

async def delete_temp_birth_data(vk_id: int | str):
    """Удаляет данные рождения из Redis"""
    await redis_client.delete(f"user:birth_data:{vk_id}")

async def clear_all_pii(vk_id: int | str):
    """Полная очистка всех персональных данных из Redis"""
    keys = [
        f"user:birth_data:{vk_id}",
        f"user:latest_reading:{vk_id}",
        f"user:readings_history:{vk_id}",
        f"user:core_profile:{vk_id}",
        f"user:destiny_card:{vk_id}"
    ]
    for k in keys:
        await redis_client.delete(k)

async def set_latest_reading(vk_id: int | str, text: str, data: dict = None, ttl: int = 86400):
    """Сохраняет последний разбор в Redis на 24 часа"""
    payload = {"text": text, "data": data or {}}
    await redis_client.set(f"user:latest_reading:{vk_id}", json.dumps(payload, ensure_ascii=False), ex=ttl)

async def get_latest_reading(vk_id: int | str) -> dict | None:
    """Получает последний разбор из Redis"""
    res = await redis_client.get(f"user:latest_reading:{vk_id}")
    if res:
        try:
            return json.loads(res)
        except Exception:
            pass
    return None

TAROT_NAMES_CACHE = None

async def record_ai_request():
    """Записывает таймстамп запроса к ИИ для подсчета RPM"""
    import time
    import random
    now = time.time()
    key = "stats:ai_requests_rpm"
    member = f"{now}:{random.random()}"
    pipe = redis_client.pipeline()
    pipe.zadd(key, {member: now})
    pipe.zremrangebyscore(key, 0, now - 60)
    pipe.expire(key, 120)
    await pipe.exec()

async def acquire_ai_slot(limit: int = 15, wait: bool = True) -> bool:
    """
    Проверяет лимит RPM и резервирует слот для запроса.
    Если wait=True, ждет освобождения слота.
    """
    import time
    import random
    import asyncio
    from loguru import logger

    key = "stats:ai_requests_rpm"

    # Lua скрипт для атомарной проверки и записи
    lua_script = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local limit = tonumber(ARGV[2])
    local member = ARGV[3]

    redis.call('ZREMRANGEBYSCORE', key, 0, now - 60)
    local count = redis.call('ZCARD', key)

    if count < limit then
        redis.call('ZADD', key, now, member)
        redis.call('EXPIRE', key, 120)
        return 1
    else
        return 0
    end
    """

    while True:
        now = time.time()
        member = f"{now}:{random.random()}"

        try:
            # В upstash_redis eval принимает (script, keys, args)
            res = await redis_client.eval(lua_script, [key], [now, limit, member])
            if res == 1:
                return True
        except Exception as e:
            logger.error(f"Ошибка в acquire_ai_slot (Lua): {e}")
            # Фолбэк на не-атомарную логику если Lua упал
            count = await get_ai_rpm()
            if count < limit:
                await record_ai_request()
                return True

        if not wait:
            return False

        await asyncio.sleep(2) # Ждем и пробуем снова

async def get_ai_rpm() -> int:
    """Возвращает количество запросов к ИИ за последнюю минуту"""
    import time
    now = time.time()
    key = "stats:ai_requests_rpm"
    try:
        await redis_client.zremrangebyscore(key, 0, now - 60)
        count = await redis_client.zcard(key)
        return int(count or 0)
    except Exception:
        return 0

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
