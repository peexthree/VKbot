import asyncio
import json

import aiohttp
from typing import Optional
from loguru import logger
from database.config import URL, KEY, HEADERS, TABLE_NAME

session: Optional[aiohttp.ClientSession] = None

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

async def get_user(vk_id: int):
    """Профиль юзера с кэшем в Redis на 45с (ускорение: Supabase RT ~0.3с
    на каждый кликmiddleware+обработчик -> один Redis hit ~0.05с).
    Балансы всегда атомарны через RPC, поэтому кэш безопасен для отрисовки;
    при любом изменении данных вызывается invalidate_user_cache."""
    if not URL or not KEY or session is None: return None

    from cache import redis_client, USER_CACHE_TTL

    try:
        cached = await redis_client.get(f"ucache:{vk_id}")
        if cached:
            user = json.loads(cached)
            # Незакоммиченная миграция bonuses обходит кэш (разовая конвертация)
            if user.get("bonuses") is None:
                return user
    except Exception:
        pass

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
                        asyncio.create_task(update_user(vk_id, {"balance": new_balance, "bonuses": None}))
                        return user
                    try:
                        await redis_client.set(
                            f"ucache:{vk_id}", json.dumps(user, ensure_ascii=False), ex=USER_CACHE_TTL
                        )
                    except Exception:
                        pass
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
                try:
                    return await r.json()
                except:
                    return True
            else:
                text = await r.text()
                logger.error(f"Supabase RPC error {func_name}: {r.status} - {text}")
    except Exception as e:
        logger.error(f"Ошибка в call_rpc {func_name}: {e}")
    return None
