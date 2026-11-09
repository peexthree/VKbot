import asyncio
import json
import os
import random
import time
from typing import Any, Optional

import aiofiles
from loguru import logger
from upstash_redis.asyncio import Redis

redis_client = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL", ""),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN", ""),
)

# =====================================================================
# IN-MEMORY LOCKS (Мгновенные блокировки без сетевых задержек)
# Render работает в 1 процессе (WEB_CONCURRENCY=1), поэтому in-memory
# лок исключает зависание кнопок, сетевые ошибки Upstash и лимиты квот.
# =====================================================================
_memory_locks: dict[str, float] = {}


async def acquire_lock(vk_id: int | str, ttl: int = 30) -> bool:
    """Мгновенный in-memory лок (0 сетевых вызовов, 0 задержки, исключает залипание кнопок).
    Поскольку Render работает с 1 воркером (WEB_CONCURRENCY=1), in-memory лок
    гарантирует синхронизацию действий юзера и не расходует квоту Upstash."""
    now = time.time()
    key = str(vk_id)

    # Периодическая очистка устаревших локов (разгрузка памяти)
    if len(_memory_locks) > 500:
        expired = [k for k, exp in _memory_locks.items() if exp <= now]
        for k in expired:
            _memory_locks.pop(k, None)

    current_exp = _memory_locks.get(key, 0.0)
    if now < current_exp:
        return False

    _memory_locks[key] = now + float(ttl)
    return True


async def release_lock(vk_id: int | str):
    """Мгновенное освобождение in-memory лока"""
    _memory_locks.pop(str(vk_id), None)


# =====================================================================
# IN-MEMORY THROTTLING & EVENT DEDUPLICATION
# =====================================================================
_throttle_map: dict[str, float] = {}
_throttle_warn_map: dict[str, float] = {}
_seen_events: dict[str, float] = {}


async def check_throttle(vk_id: int | str, cooldown: float = 0.8) -> bool:
    """Мгновенный in-memory троттлинг: True если юзер кликает слишком часто (дроп), False если разрешено."""
    now = time.time()
    key = str(vk_id)

    if len(_throttle_map) > 1000:
        expired = [k for k, t in _throttle_map.items() if now - t > 10.0]
        for k in expired:
            _throttle_map.pop(k, None)

    last_ts = _throttle_map.get(key, 0.0)
    if (now - last_ts) < cooldown:
        return True

    _throttle_map[key] = now
    return False


async def check_and_set_throttle_warning(vk_id: int | str, cooldown: float = 10.0) -> bool:
    """Мгновенный in-memory кулдаун предупреждений: True если предупреждение разрешено, False если на паузе."""
    now = time.time()
    key = str(vk_id)

    last_warn = _throttle_warn_map.get(key, 0.0)
    if (now - last_warn) < cooldown:
        return False

    _throttle_warn_map[key] = now
    return True


def check_and_mark_event_seen(event_key: str, ttl: float = 60.0) -> bool:
    """Проверяет и помечает событие в in-memory кэше.
    Возвращает True если событие НОВОЕ (впервые видим), False если дубликат (уже обработано)."""
    now = time.time()
    if len(_seen_events) > 2000:
        cutoff = now - 120.0
        for k in list(_seen_events.keys()):
            if _seen_events[k] < cutoff:
                del _seen_events[k]

    exp = _seen_events.get(event_key, 0.0)
    if now < exp:
        return False
    _seen_events[event_key] = now + ttl
    return True


# =====================================================================
# SYSTEM CONFIG (Флаги техобслуживания, прокси, прогрева)
# In-memory кэш на 60 сек исключает спам запросами к Upstash на каждый клик/сообщение.
# =====================================================================
_system_config_cache: dict[str, tuple[float, str]] = {}
SYSTEM_CONFIG_CACHE_TTL = 60.0


async def get_system_config(key: str, default: str | None = None) -> str | None:
    """Получает системный флаг с in-memory кэшированием на 60 секунд.
    Исключает постоянные сетевые запросы к Upstash на каждое сообщение."""
    now = time.time()
    cached = _system_config_cache.get(key)
    if cached and (now - cached[0]) < SYSTEM_CONFIG_CACHE_TTL:
        return cached[1]

    try:
        val = await redis_client.get(key)
        if isinstance(val, bytes):
            val = val.decode("utf-8")
        elif val is not None:
            val = str(val)
        else:
            val = default
        _system_config_cache[key] = (now, val)
        return val
    except Exception as e:
        logger.warning(f"Error fetching system config '{key}' from Redis (fallback used): {e}")
        if cached:
            return cached[1]
        return default


async def set_system_config(key: str, value: Any):
    """Устанавливает системный флаг: сразу в память и в Redis."""
    str_val = str(int(value)) if isinstance(value, bool) else str(value)
    _system_config_cache[key] = (time.time(), str_val)
    try:
        await redis_client.set(key, str_val)
    except Exception as e:
        logger.warning(f"Error persisting system config '{key}' to Redis: {e}")


# =====================================================================
# FSM STATE (Шаги пользователя)
# Согласно AGENTS.md, FSM сохраняется в Redis для выживания при рестартах Render.
# Внутри процесса используется L1 in-memory кэш для мгновенного чтения.
# =====================================================================
_fsm_l1: dict[str, str] = {}


async def set_fsm_state(vk_id: int | str, state_data: str, ttl: int = 86400):
    key = str(vk_id)
    if not state_data:
        _fsm_l1.pop(key, None)
        try:
            await redis_client.delete(f"fsm:{vk_id}")
        except Exception as e:
            logger.debug(f"Error deleting fsm from Redis for {vk_id}: {e}")
    else:
        _fsm_l1[key] = state_data
        try:
            await redis_client.set(f"fsm:{vk_id}", state_data, ex=ttl)
        except Exception as e:
            logger.warning(f"Error setting fsm in Redis for {vk_id}: {e}")


async def get_fsm_state(vk_id: int | str) -> str | None:
    key = str(vk_id)
    if key in _fsm_l1:
        return _fsm_l1[key]

    try:
        val = await redis_client.get(f"fsm:{vk_id}")
        if isinstance(val, bytes):
            val = val.decode("utf-8")
        if val:
            _fsm_l1[key] = val
        return val
    except Exception as e:
        logger.debug(f"Error getting fsm from Redis for {vk_id}: {e}")
        return None


# =====================================================================
# L1 IN-MEMORY КЭШ ДЛЯ ДАННЫХ ПОЛЬЗОВАТЕЛЯ
# =====================================================================
_birth_data_l1: dict[str, tuple[float, dict]] = {}
_destiny_card_l1: dict[str, tuple[float, dict]] = {}
_latest_reading_l1: dict[str, tuple[float, dict]] = {}
_teaser_l1: dict[str, tuple[float, dict]] = {}
_readings_history_l1: dict[str, tuple[float, list]] = {}
_core_profile_l1: dict[str, tuple[float, str]] = {}

L1_CACHE_TTL = 1800.0  # 30 минут локального кэша


async def set_temp_birth_data(vk_id: int | str, data: dict, ttl: int = 86400):
    """Сохраняет данные рождения в L1 кэш и Redis на 24 часа"""
    key = str(vk_id)
    _birth_data_l1[key] = (time.time(), data)
    try:
        await redis_client.set(
            f"user:birth_data:{vk_id}", json.dumps(data, ensure_ascii=False), ex=ttl
        )
    except Exception as e:
        logger.debug(f"Redis set_temp_birth_data error for {vk_id}: {e}")


async def get_temp_birth_data(vk_id: int | str) -> dict | None:
    """Получает данные рождения: сначала L1 кэш (0мс), затем Redis"""
    key = str(vk_id)
    cached = _birth_data_l1.get(key)
    now = time.time()
    if cached and (now - cached[0]) < L1_CACHE_TTL:
        return cached[1]

    try:
        res = await redis_client.get(f"user:birth_data:{vk_id}")
        if res:
            if isinstance(res, bytes):
                res = res.decode("utf-8")
            data = json.loads(res)
            _birth_data_l1[key] = (now, data)
            return data
    except Exception as e:
        logger.debug(f"Redis get_temp_birth_data error for {vk_id}: {e}")

    return None


async def delete_temp_birth_data(vk_id: int | str):
    """Удаляет данные рождения из L1 кэша и Redis"""
    key = str(vk_id)
    _birth_data_l1.pop(key, None)
    try:
        await redis_client.delete(f"user:birth_data:{vk_id}")
    except Exception:
        pass


async def get_core_profile(vk_id: int | str) -> str:
    """Получает core_profile: сначала L1 кэш (0мс), затем Redis"""
    key = str(vk_id)
    cached = _core_profile_l1.get(key)
    now = time.time()
    if cached and (now - cached[0]) < L1_CACHE_TTL:
        return cached[1]

    try:
        res = await redis_client.get(f"user:core_profile:{vk_id}")
        val = res.decode() if isinstance(res, bytes) else (res or "")
        _core_profile_l1[key] = (now, val)
        return val
    except Exception as e:
        logger.debug(f"Redis get_core_profile error for {vk_id}: {e}")
        return ""


async def set_destiny_card_data(vk_id: int | str, data: dict, ttl: int = 86400):
    """Сохраняет карту судьбы в L1 кэш и Redis на 24 часа"""
    key = str(vk_id)
    _destiny_card_l1[key] = (time.time(), data)
    try:
        await redis_client.set(
            f"user:destiny_card:{vk_id}", json.dumps(data, ensure_ascii=False), ex=ttl
        )
    except Exception as e:
        logger.debug(f"Redis set_destiny_card_data error for {vk_id}: {e}")


async def get_destiny_card_data(vk_id: int | str) -> dict | None:
    """Получает карту судьбы: L1 -> Redis -> Supabase"""
    key = str(vk_id)
    cached = _destiny_card_l1.get(key)
    now = time.time()
    if cached and (now - cached[0]) < L1_CACHE_TTL:
        return cached[1]

    try:
        res = await redis_client.get(f"user:destiny_card:{vk_id}")
        if res:
            if isinstance(res, bytes):
                res = res.decode("utf-8")
            data = json.loads(res)
            _destiny_card_l1[key] = (now, data)
            return data
    except Exception as e:
        logger.debug(f"Redis get_destiny_card_data error for {vk_id}: {e}")

    # Фолбэк на Supabase
    try:
        from database import get_user

        user = await get_user(int(vk_id))
        if user and isinstance(user.get("destiny_card_data"), dict):
            data = user.get("destiny_card_data")
            if data and data.get("text"):
                await set_destiny_card_data(vk_id, data)
                return data
    except Exception as e:
        logger.error(f"Ошибка получения карты судьбы из БД для {vk_id}: {e}")
    return None


async def add_reading_to_history(vk_id: int | str, item: dict, ttl: int = 86400):
    """Добавляет разбор в историю в L1 и Redis"""
    history = await get_readings_history(vk_id)
    history.append(item)
    key = str(vk_id)
    _readings_history_l1[key] = (time.time(), history)
    try:
        await redis_client.set(
            f"user:readings_history:{vk_id}",
            json.dumps(history, ensure_ascii=False),
            ex=ttl,
        )
    except Exception as e:
        logger.debug(f"Redis add_reading_to_history error for {vk_id}: {e}")


async def get_readings_history(vk_id: int | str) -> list:
    """Получает историю разборов: L1 -> Redis -> Supabase"""
    key = str(vk_id)
    cached = _readings_history_l1.get(key)
    now = time.time()
    if cached and (now - cached[0]) < L1_CACHE_TTL:
        return cached[1]

    try:
        res = await redis_client.get(f"user:readings_history:{vk_id}")
        if res:
            if isinstance(res, bytes):
                res = res.decode("utf-8")
            data = json.loads(res)
            if isinstance(data, list):
                _readings_history_l1[key] = (now, data)
                return data
    except Exception as e:
        logger.debug(f"Redis get_readings_history error for {vk_id}: {e}")

    # Фолбэк на Supabase
    try:
        from database import get_user

        user = await get_user(int(vk_id))
        if user:
            history = user.get("readings_history") or []
            if not isinstance(history, list):
                history = []
            _readings_history_l1[key] = (now, history)
            try:
                await redis_client.set(
                    f"user:readings_history:{vk_id}",
                    json.dumps(history, ensure_ascii=False),
                    ex=86400,
                )
            except Exception:
                pass
            return history
    except Exception as e:
        logger.error(f"Ошибка получения истории из Supabase для {vk_id}: {e}")
    return []


async def set_latest_reading(
    vk_id: int | str, text: str, data: dict = None, ttl: int = 86400
):
    """Сохраняет последний разбор в L1 и Redis на 24 часа"""
    payload = {"text": text, "data": data or {}}
    key = str(vk_id)
    _latest_reading_l1[key] = (time.time(), payload)
    try:
        await redis_client.set(
            f"user:latest_reading:{vk_id}",
            json.dumps(payload, ensure_ascii=False),
            ex=ttl,
        )
    except Exception as e:
        logger.debug(f"Redis set_latest_reading error for {vk_id}: {e}")


async def get_latest_reading(vk_id: int | str) -> dict | None:
    """Получает последний разбор: L1 -> Redis"""
    key = str(vk_id)
    cached = _latest_reading_l1.get(key)
    now = time.time()
    if cached and (now - cached[0]) < L1_CACHE_TTL:
        return cached[1]

    try:
        res = await redis_client.get(f"user:latest_reading:{vk_id}")
        if res:
            if isinstance(res, bytes):
                res = res.decode("utf-8")
            data = json.loads(res)
            _latest_reading_l1[key] = (now, data)
            return data
    except Exception as e:
        logger.debug(f"Redis get_latest_reading error for {vk_id}: {e}")

    return None


async def clear_all_pii(vk_id: int | str):
    """Полная очистка всех персональных данных из памяти и Redis"""
    key = str(vk_id)
    _birth_data_l1.pop(key, None)
    _destiny_card_l1.pop(key, None)
    _latest_reading_l1.pop(key, None)
    _readings_history_l1.pop(key, None)
    _core_profile_l1.pop(key, None)
    _teaser_l1.pop(key, None)

    keys = [
        f"user:birth_data:{vk_id}",
        f"user:latest_reading:{vk_id}",
        f"user:readings_history:{vk_id}",
        f"user:core_profile:{vk_id}",
        f"user:destiny_card:{vk_id}",
        f"teaser:{vk_id}",
    ]
    for k in keys:
        try:
            await redis_client.delete(k)
        except Exception:
            pass


# =====================================================================
# TAROT NAMES CACHE (In-Memory)
# =====================================================================
TAROT_NAMES_CACHE = None


async def get_tarot_names() -> dict:
    global TAROT_NAMES_CACHE
    if TAROT_NAMES_CACHE is not None:
        return TAROT_NAMES_CACHE

    try:
        async with aiofiles.open("tarot_ids.json", "r", encoding="utf-8") as f:
            content = await f.read()
            names = json.loads(content)
            TAROT_NAMES_CACHE = names
            return names
    except Exception as e:
        logger.error(f"Ошибка загрузки имен таро из файла: {e}")

    try:
        cached = await redis_client.get("system:tarot_names")
        if cached:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            TAROT_NAMES_CACHE = json.loads(cached)
            return TAROT_NAMES_CACHE
    except Exception as e:
        logger.debug(f"Ошибка получения имен таро из Redis: {e}")

    return {}


# =====================================================================
# AI RPM LIMITER (Защита от превышения квоты API)
# =====================================================================
async def record_ai_request():
    """Записывает таймстамп запроса к ИИ для подсчета RPM"""
    now = time.time()
    key = "stats:ai_requests_rpm"
    member = f"{now}:{random.random()}"
    try:
        pipe = redis_client.pipeline()
        pipe.zadd(key, {member: now})
        pipe.zremrangebyscore(key, 0, now - 60)
        pipe.expire(key, 120)
        await pipe.exec()
    except Exception as e:
        logger.debug(f"Error in record_ai_request: {e}")


async def acquire_ai_slot(limit: int = 15, wait: bool = True) -> bool:
    """Проверяет лимит RPM и резервирует слот для запроса."""
    key = "stats:ai_requests_rpm"
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
            res = await redis_client.eval(lua_script, [key], [now, limit, member])
            if res == 1:
                return True
        except Exception as e:
            logger.debug(f"Ошибка в acquire_ai_slot (Lua): {e}")
            count = await get_ai_rpm()
            if count < limit:
                await record_ai_request()
                return True

        if not wait:
            return False

        await asyncio.sleep(2)


async def get_ai_rpm() -> int:
    """Возвращает количество запросов к ИИ за последнюю минуту"""
    now = time.time()
    key = "stats:ai_requests_rpm"
    try:
        await redis_client.zremrangebyscore(key, 0, now - 60)
        count = await redis_client.zcard(key)
        return int(count or 0)
    except Exception:
        return 0


# =====================================================================
# GOD MODE (Пасхалка 'лайн голос')
# =====================================================================
GOD_MODE_ALLOWED_KEY = "godmode:allowed"
_god_mode_cache: set[str] = set()
_god_mode_cache_ts: float = 0.0


async def god_mode_is_allowed(vk_id: int | str) -> bool:
    global _god_mode_cache, _god_mode_cache_ts
    now = time.time()
    if now - _god_mode_cache_ts > 300.0 or not _god_mode_cache:
        try:
            members = await redis_client.smembers(GOD_MODE_ALLOWED_KEY) or []
            _god_mode_cache = {
                (m.decode() if isinstance(m, bytes) else str(m)) for m in members
            }
            _god_mode_cache_ts = now
        except Exception as e:
            logger.debug(f"Error refreshing god_mode cache: {e}")

    return str(vk_id) in _god_mode_cache


async def god_mode_allow(vk_id: int | str) -> bool:
    global _god_mode_cache
    _god_mode_cache.add(str(vk_id))
    try:
        await redis_client.sadd(GOD_MODE_ALLOWED_KEY, str(vk_id))
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления {vk_id} в god_mode список: {e}")
        return False


async def god_mode_disallow(vk_id: int | str) -> bool:
    global _god_mode_cache
    _god_mode_cache.discard(str(vk_id))
    try:
        await redis_client.srem(GOD_MODE_ALLOWED_KEY, str(vk_id))
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления {vk_id} из god_mode списка: {e}")
        return False


async def god_mode_list() -> list[int]:
    try:
        members = await redis_client.smembers(GOD_MODE_ALLOWED_KEY) or []
        result = []
        for m in members:
            if isinstance(m, bytes):
                m = m.decode()
            try:
                result.append(int(str(m)))
            except ValueError:
                continue
        return sorted(result)
    except Exception as e:
        logger.error(f"Ошибка чтения god_mode списка: {e}")
        return []


# =====================================================================
# USER CACHE INVALIDATION & TEASERS
# =====================================================================
PENDING_TEASER_TTL = 604800  # 7 дней
USER_CACHE_TTL = 45  # для обратной совместимости


async def invalidate_user_cache(vk_id: int | str):
    """Сбрасывает кэш профиля в оперативной памяти после обновления в БД."""
    try:
        from database.core import _user_cache

        _user_cache.pop(int(vk_id), None)
    except Exception:
        pass


async def set_pending_teaser(vk_id: int | str, data: dict, ttl: int = PENDING_TEASER_TTL):
    """Сохраняет незавершенный Hook&Pay тизер в L1 и Redis"""
    key = str(vk_id)
    _teaser_l1[key] = (time.time(), data)
    try:
        await redis_client.set(
            f"teaser:{vk_id}", json.dumps(data, ensure_ascii=False), ex=ttl
        )
    except Exception as e:
        logger.debug(f"Redis set_pending_teaser error for {vk_id}: {e}")


async def get_pending_teaser(vk_id: int | str) -> dict | None:
    """Читает незавершенный тизер: L1 -> Redis"""
    key = str(vk_id)
    cached = _teaser_l1.get(key)
    now = time.time()
    if cached and (now - cached[0]) < L1_CACHE_TTL:
        return cached[1]

    try:
        res = await redis_client.get(f"teaser:{vk_id}")
        if res:
            if isinstance(res, bytes):
                res = res.decode("utf-8")
            data = json.loads(res)
            _teaser_l1[key] = (now, data)
            return data
    except Exception as e:
        logger.debug(f"Redis get_pending_teaser error for {vk_id}: {e}")

    return None


async def pop_pending_teaser(vk_id: int | str) -> dict | None:
    """Читает и удаляет незавершенный тизер (после оплаты)"""
    key = str(vk_id)
    teaser = await get_pending_teaser(vk_id)
    _teaser_l1.pop(key, None)
    try:
        await redis_client.delete(f"teaser:{vk_id}")
    except Exception:
        pass
    return teaser


async def get_birth_data_or_fallback(
    vk_id: int | str, user: dict = None
) -> dict | None:
    """
    Возвращает данные рождения из кэша. Если их там нет, берет из профиля Supabase (core_profile)
    и кэширует, исключая повторный ввод данных.
    """
    data = await get_temp_birth_data(vk_id)
    if data:
        return data

    if not user:
        try:
            from database import get_user

            user = await get_user(int(vk_id))
        except Exception:
            pass

    if user and user.get("core_profile"):
        cp = user.get("core_profile", "").strip()
        parts = cp.split(maxsplit=2)
        parsed = {}
        if len(parts) >= 3:
            parsed = {"date": parts[0], "time": parts[1], "city": parts[2]}
        elif len(parts) == 2:
            parsed = {"date": parts[0], "time": "12:00", "city": parts[1]}
        elif len(parts) == 1:
            parsed = {"date": parts[0], "time": "12:00", "city": ""}

        if parsed and parsed.get("date"):
            await set_temp_birth_data(vk_id, parsed)
            return parsed

    return None
