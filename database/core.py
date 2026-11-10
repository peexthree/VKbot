import asyncio
import time

import aiohttp
from typing import Optional
from loguru import logger
from database.config import URL, KEY, HEADERS, TABLE_NAME

session: Optional[aiohttp.ClientSession] = None
# Сильные ссылки на фоновые таски: create_task без ссылки может быть собран GC
# до завершения (аудит 2026-11-10)
_background_tasks: set = set()

async def init_db():
    global session
    if session is None:
        session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100),
            # Таймаут по умолчанию у aiohttp ~5 минут: зависший вызов Supabase
            # блокирует обработчик, пока истекает Redis-лок (см. audit 2026-11)
            timeout=aiohttp.ClientTimeout(total=30),
        )

async def close_db():
    global session
    if session is not None:
        await session.close()
        session = None

# In-process кэш профиля (один воркер на Render): 0 сетевых вызовов на чтение.
# Раньше кэш жил в Upstash - каждый клик гонял 1-2 REST-вызова Redis
# (~100-200мс + квота команд), при лаге Upstash клики умирали.
_user_cache: dict[int, tuple[float, dict]] = {}
_USER_CACHE_TTL = 30.0


def _local_cache_get(vk_id: int) -> dict | None:
    entry = _user_cache.get(vk_id)
    if not entry:
        return None
    ts, user = entry
    if time.time() - ts > _USER_CACHE_TTL:
        _user_cache.pop(vk_id, None)
        return None
    if user.get("bonuses") is not None:
        return None  # незакоммиченная миграция bonuses - идём в БД
    return user


def _local_cache_put(vk_id: int, user: dict):
    if len(_user_cache) > 5000:  # защита от роста памяти
        _user_cache.clear()
    _user_cache[vk_id] = (time.time(), user)


async def get_user(vk_id: int):
    """Профиль юзера: in-memory кэш 30с (0 сети) -> Supabase.
    Балансы меняются только атомарными RPC, при любом изменении профиля
    кэш сбрасывается (update_user/add_energy/spend/promo)."""
    if not URL or not KEY or session is None: return None

    cached = _local_cache_get(vk_id)
    if cached is not None:
        return cached

    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                if data:
                    user = data[0]
                    if "bonuses" in user and user["bonuses"] is not None:
                        new_balance = (user.get("balance", 0) * 10) + user["bonuses"]
                        user["balance"] = new_balance
                        del user["bonuses"]
                        from .users import update_user # Local import to avoid circularity if needed
                        _task = asyncio.create_task(update_user(vk_id, {"balance": new_balance, "bonuses": None}))
                        _background_tasks.add(_task)
                        _task.add_done_callback(_background_tasks.discard)
                        return user
                    _local_cache_put(vk_id, user)
                    return user
            else: logger.error(f"Supabase error in get_user: {r.status}")
    except Exception as e: logger.error(f"Ошибка в get_user: {e}")
    return None

async def get_all_users():
    """Все пользователи с пагинацией: без Range-заголовка PostgREST молча
    обрезает ответ до 1000 строк (см. audit 2026-11)"""
    if not URL or not KEY or session is None: return []
    users = []
    page_size = 1000
    offset = 0
    try:
        while True:
            headers = HEADERS.copy()
            headers["Range"] = f"{offset}-{offset + page_size - 1}"
            async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?select=*", headers=headers) as r:
                if r.status not in (200, 206):
                    logger.error(f"Supabase error in get_all_users: {r.status}")
                    break
                data = await r.json()
                if not data:
                    break
                users.extend(data)
                if len(data) < page_size:
                    break
                offset += page_size
    except Exception as e: logger.error(f"Ошибка в get_all_users: {e}")
    return users

async def get_user_by_cipher(cipher: str):
    """Поиск пользователя по теневому шифру"""
    if not URL or not KEY or session is None: return None
    try:
        # Используем параметры запроса для безопасной передачи данных (защита от инъекций в PostgREST)
        params = {
            "purchased_sections->>shadow_cipher": f"eq.{cipher.upper()}"
        }
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}", headers=HEADERS, params=params) as r:
            if r.status == 200:
                data = await r.json()
                if data: return data[0]
    except Exception as e: logger.error(f"Ошибка в get_user_by_cipher: {e}")
    return None

async def call_rpc(func_name: str, params: dict):
    """Вызов хранимой процедуры (RPC) в Supabase"""
    if not URL or not KEY or session is None: return None
    try:
        async with session.post(f"{URL}/rest/v1/rpc/{func_name}", headers=HEADERS, json=params) as r:
            if r.status in (200, 201, 204):
                # FIX (аудит 2026-11-10): 204 (void-RPC вроде increment_user_balance)
                # - это успех с пустым телом, а не ошибка парсинга; bare except
                # глотал и CancelledError
                if r.status == 204:
                    return True
                try:
                    return await r.json()
                except Exception:
                    return True
            else:
                text = await r.text()
                logger.error(f"Supabase RPC error {func_name}: {r.status} - {text}")
    except Exception as e:
        logger.error(f"Ошибка в call_rpc {func_name}: {e}")
    return None
