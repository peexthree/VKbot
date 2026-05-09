import json
import os
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from cache import get_fsm_state, set_fsm_state

URL = os.environ.get("SUPABASE_URL", "")
KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

TABLE_NAME = "vk_esoteric_users"
FSM_TABLE = "user_fsm"
session: Optional[aiohttp.ClientSession] = None


async def init_db():
    """Инициализация пула соединений"""
    global session
    if session is None:
        connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=15)
        session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        logger.info("Supabase session initialized")


async def close_db():
    """Корректное закрытие сессии (вызывается при shutdown)"""
    global session
    if session:
        await session.close()
        session = None
        logger.info("Supabase session closed")


async def _supabase_request(method: str, endpoint: str, **kwargs) -> Optional[Dict | List]:
    """Универсальный запрос к Supabase (DRY)"""
    if not URL or not KEY or session is None:
        logger.error("Supabase не настроен")
        return None

    url = f"{URL}/rest/v1/{endpoint}"
    try:
        async with session.request(method, url, headers=HEADERS, **kwargs) as r:
            if r.status in (200, 201, 204):
                if r.content_type == "application/json":
                    return await r.json()
                return None
            else:
                text = await r.text()
                logger.error(f"Supabase error {method} {endpoint}: {r.status} {text}")
                return None
    except Exception as e:
        logger.error(f"Supabase request error {method} {endpoint}: {e}")
        return None


async def migrate_legacy_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Одноразовая миграция bonuses → balance"""
    if "bonuses" in user and user["bonuses"] is not None:
        new_balance = (user.get("balance", 0) * 10) + user["bonuses"]
        user["balance"] = new_balance
        del user["bonuses"]
        # Обновляем в фоне
        asyncio.create_task(update_user(user["vk_id"], {"balance": new_balance, "bonuses": None}))
        logger.info(f"Migrated legacy bonuses for vk_id={user['vk_id']}")
    return user


async def get_user(vk_id: int) -> Optional[Dict[str, Any]]:
    data = await _supabase_request("GET", f"{TABLE_NAME}?vk_id=eq.{vk_id}")
    if data and isinstance(data, list) and data:
        user = await migrate_legacy_user(data[0])
        return user
    return None


async def get_all_users(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    """Все пользователи с пагинацией"""
    data = await _supabase_request("GET", f"{TABLE_NAME}?limit={limit}&offset={offset}")
    return data if isinstance(data, list) else []


async def get_all_subscribed_users(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    """Только пользователи с полной картой"""
    data = await _supabase_request("GET", f"{TABLE_NAME}?has_full_chart=eq.true&limit={limit}&offset={offset}")
    return data if isinstance(data, list) else []


async def get_inactive_free_users(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    """Пользователи без полной карты (для кармических пушей)"""
    data = await _supabase_request("GET", f"{TABLE_NAME}?has_full_chart=eq.false&limit={limit}&offset={offset}")
    return data if isinstance(data, list) else []


async def create_user(vk_id: int, birth_date: str, birth_time: str, birth_city: str) -> Optional[Dict[str, Any]]:
    payload = {
        "vk_id": vk_id,
        "birth_date": birth_date,
        "birth_time": birth_time,
        "birth_city": birth_city,
        "partners": [],
        "has_full_chart": False,
        "purchased_sections": {"sex": False, "money": False, "shadow": False, "final": False},
        "balance": 0,
        "active_skin": "olesya",
        "purchased_skins": [],
        "transit_trial_days": 0,
        "transit_sub_expires_at": None,
        "bonuses": None,
        "last_daily_bonus_date": None,
        "last_active_date": None,
        "unlocked_cards": {},
        "weekly_log": [],
        "visit_streak": 0,
        "tags": []
    }
    data = await _supabase_request("POST", TABLE_NAME, json=payload)
    if data and isinstance(data, list) and data:
        logger.info(f"Создан пользователь vk_id={vk_id}")
        return data[0]
    return None


async def delete_user(vk_id: int) -> bool:
    data = await _supabase_request("DELETE", f"{TABLE_NAME}?vk_id=eq.{vk_id}")
    success = data is not None
    if success:
        logger.info(f"Удалён пользователь vk_id={vk_id}")
    return success


async def update_user(vk_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = await _supabase_request("PATCH", f"{TABLE_NAME}?vk_id=eq.{vk_id}", json=updates)
    if data and isinstance(data, list) and data:
        logger.info(f"Обновлён пользователь vk_id={vk_id}")
        return data[0]
    return None


async def check_and_save_transaction(transaction_id: str, vk_id: int, amount: int) -> bool:
    """Защита от фрода + сохранение транзакции"""
    # Проверяем существование
    existing = await _supabase_request(
        "GET",
        f"events?action=eq.vkpay_transaction&metadata->>transaction_id=eq.{transaction_id}"
    )
    if existing and isinstance(existing, list) and existing:
        logger.warning(f"Fraud protection: transaction {transaction_id} already exists")
        return False

    payload = {
        "user_id": vk_id,
        "action": "vkpay_transaction",
        "metadata": {"transaction_id": transaction_id, "amount": amount}
    }
    result = await _supabase_request("POST", "events", json=payload)
    return result is not None


# ====================== STATE (FSM) ======================
async def get_user_state(vk_id: int) -> Optional[str]:
    return await get_fsm_state(vk_id)


async def set_user_state(vk_id: int, state: str) -> bool:
    return await set_fsm_state(vk_id, state)
