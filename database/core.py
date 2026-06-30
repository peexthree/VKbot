import aiohttp
from typing import Optional
from loguru import logger
from database.config import URL, KEY, HEADERS, TABLE_NAME

session: Optional[aiohttp.ClientSession] = None

async def init_db():
    global session
    if session is None:
        session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100))

async def close_db():
    global session
    if session is not None:
        await session.close()
        session = None

async def get_user(vk_id: int):
    if not URL or not KEY or session is None: return None
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
                        import asyncio
                        from .users import update_user # Local import to avoid circularity if needed
                        asyncio.create_task(update_user(vk_id, {"balance": new_balance, "bonuses": None}))
                    return user
            else: logger.error(f"Supabase error in get_user: {r.status}")
    except Exception as e: logger.error(f"Ошибка в get_user: {e}")
    return None

async def get_all_users():
    if not URL or not KEY or session is None: return []
    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}", headers=HEADERS) as r:
            if r.status == 200: return await r.json()
    except Exception as e: logger.error(f"Ошибка в get_all_users: {e}")
    return []

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
