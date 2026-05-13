import json
import os
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger

from cache import get_fsm_state, set_fsm_state

URL = os.environ.get("SUPABASE_URL", "")
KEY = os.environ.get("SUPABASE_KEY", "")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}
TABLE_NAME = "vk_esoteric_users"
FSM_TABLE = "user_fsm"

session: Optional[aiohttp.ClientSession] = None


async def init_db():
    global session
    if session is None:
        session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=100))


async def get_user(vk_id: int) -> Optional[Dict[str, Any]]:
    if not URL or not KEY or session is None:
        return None
    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                if data:
                    user = data[0]
                    # Миграция старого поля bonuses → balance (on-the-fly)
                    if "bonuses" in user and user["bonuses"] is not None:
                        new_balance = (user.get("balance", 0) * 10) + user["bonuses"]
                        user["balance"] = new_balance
                        del user["bonuses"]
                        # Асинхронно обновляем в БД
                        import asyncio
                        asyncio.create_task(update_user(vk_id, {"balance": new_balance, "bonuses": None}))
                    return user
            else:
                logger.error(f"Supabase error in get_user: {r.status} {await r.text()}")
            return None
    except Exception as e:
        logger.error(f"Ошибка в get_user: {str(e)}")
        return None


async def get_all_subscribed_users() -> list[Dict[str, Any]]:
    """Получает список всех подписанных пользователей для утренних прогнозов"""
    if not URL or not KEY or session is None:
        return []
    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?has_full_chart=eq.true", headers=HEADERS) as r:
            if r.status == 200:
                return await r.json()
            else:
                logger.error(f"Supabase error in get_all_subscribed_users: {r.status} {await r.text()}")
            return []
    except Exception as e:
        logger.error(f"Ошибка в get_all_subscribed_users: {str(e)}")
        return []


async def get_all_users() -> list[Dict[str, Any]]:
    """Получает список всех пользователей"""
    if not URL or not KEY or session is None:
        return []
    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}", headers=HEADERS) as r:
            if r.status == 200:
                return await r.json()
            else:
                logger.error(f"Supabase error in get_all_users: {r.status} {await r.text()}")
            return []
    except Exception as e:
        logger.error(f"Ошибка в get_all_users: {str(e)}")
        return []


async def get_inactive_free_users() -> list[Dict[str, Any]]:
    """Получает пользователей, которые не купили разбор, для кармических пушей"""
    if not URL or not KEY or session is None:
        return []
    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?has_full_chart=eq.false", headers=HEADERS) as r:
            if r.status == 200:
                return await r.json()
            else:
                logger.error(f"Supabase error in get_inactive_free_users: {r.status} {await r.text()}")
            return []
    except Exception as e:
        logger.error(f"Ошибка в get_inactive_free_users: {str(e)}")
        return []


async def create_user(
    vk_id: int,
    birth_date: str,
    birth_time: str,
    birth_city: str,
    first_name: str = ""
) -> Optional[Dict[str, Any]]:
    """Создаёт пользователя с ПОЛНОЙ актуальной схемой таблицы (31 колонка)"""
    if not URL or not KEY or session is None:
        return None

    payload = {
        "vk_id": vk_id,
        "birth_date": birth_date,
        "birth_time": birth_time,
        "birth_city": birth_city,
        "free_teaser_used": False,
        "is_subscribed": False,
        "compatibility_balance": 0,
        "core_profile": "",
        "partners": [],
        "free_card_used": False,
        "purchased_sections": {
            "sex": False,
            "money": False,
            "shadow": False,
            "final": False,
            "sex_val": 0,
            "first_name": first_name,
            "oracle_access": False,
            "card_of_day_last_used": None
        },
        "has_full_chart": False,
        "forecast_time": None,
        "balance": 0,
        "oracle_last_used": None,
        "has_priority_access": False,
        "bonuses": None,
        "last_active_date": None,
        "active_skin": "olesya",
        "purchased_skins": [],
        "transit_trial_days": 0,
        "transit_sub_expires_at": None,
        "unlocked_cards": {},
        "weekly_log": [],
        "visit_streak": 0,
        "total_cards_received": 0,
        "last_daily_bonus_date": None,
        "welcome_bonus_received": False,
        "tags": [],
        "latest_reading_text": None,
        "latest_reading_data": {}
    }

    try:
        async with session.post(f"{URL}/rest/v1/{TABLE_NAME}", headers=HEADERS, json=payload) as r:
            if r.status in (200, 201):
                data = await r.json()
                if data:
                    logger.success(f"✅ Создан пользователь vk_id={vk_id}")
                    return data[0]
            else:
                logger.error(f"Supabase error in create_user: {r.status} {await r.text()}")
            return None
    except Exception as e:
        logger.error(f"Ошибка в create_user: {str(e)}")
        return None


async def delete_user(vk_id: int) -> bool:
    if not URL or not KEY or session is None:
        return False
    try:
        async with session.delete(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            if r.status in (200, 204):
                logger.info(f"Удален из Users: vk_id={vk_id}")
                return True
            else:
                logger.error(f"Supabase error in delete_user: {r.status} {await r.text()}")
            return False
    except Exception as e:
        logger.error(f"Ошибка в delete_user: {str(e)}")
        return False


async def update_user(vk_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not URL or not KEY or session is None:
        return None
    try:
        async with session.patch(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS, json=updates) as r:
            if r.status in (200, 204):
                data = await r.json()
                if data:
                    logger.success(f"✅ Обновлён пользователь vk_id={vk_id}")
                    return data[0]
            else:
                logger.error(f"Supabase error in update_user: {r.status} {await r.text()}")
            return None
    except Exception as e:
        logger.error(f"Ошибка в update_user: {str(e)}")
        return None


async def check_and_save_transaction(transaction_id: str, vk_id: int, amount: int) -> bool:
    """Checks if a vkpay transaction exists to prevent fraud, and saves it if unique."""
    if not URL or not KEY or session is None:
        return False
    try:
        # Check for existing transaction
        async with session.get(
            f"{URL}/rest/v1/events?action=eq.vkpay_transaction&metadata->>transaction_id=eq.{transaction_id}",
            headers=HEADERS
        ) as r:
            if r.status == 200:
                data = await r.json()
                if data:
                    logger.warning(f"Fraud protection triggered: transaction {transaction_id} already exists.")
                    return False
            else:
                logger.error(f"Supabase error in check_and_save_transaction (get): {r.status} {await r.text()}")
                return False

        # Insert new transaction
        payload = {
            "user_id": vk_id,
            "action": "vkpay_transaction",
            "metadata": {"transaction_id": transaction_id, "amount": amount}
        }
        async with session.post(f"{URL}/rest/v1/events", headers=HEADERS, json=payload) as r:
            if r.status in (200, 201, 204):
                return True
            else:
                logger.error(f"Supabase error in check_and_save_transaction (post): {r.status} {await r.text()}")
                return False
    except Exception as e:
        logger.error(f"Ошибка в check_and_save_transaction: {str(e)}")
        return False


async def get_user_state(vk_id: int) -> Optional[str]:
    from modules.bot_init import bot
    state_rec = await bot.state_dispenser.get(vk_id)
    if state_rec:
        return state_rec.payload.get("raw_json") if state_rec.payload else None
    return await get_fsm_state(vk_id)


async def set_user_state(vk_id: int, state: str) -> bool:
    from modules.bot_init import bot
    from modules.states import MyStates
    if not state:
        try:
            await bot.state_dispenser.delete(vk_id)
        except KeyError:
            pass
        await set_fsm_state(vk_id, state)
        return True

    try:
        data = json.loads(state)
        step = data.get("step", "")
    except Exception:
        step = state

    state_map = {
        "waiting_for_onboarding_data": MyStates.WAITING_FOR_ONBOARDING_DATA,
        "date": MyStates.WAITING_FOR_DATE,
        "time": MyStates.WAITING_FOR_TIME,
        "city": MyStates.WAITING_FOR_CITY,
        "confirm_data": MyStates.WAITING_CONFIRM_DATA,
        "waiting_synastry_date": MyStates.WAITING_SYNASTRY_DATE,
        "waiting_oracle_question": MyStates.WAITING_ORACLE_QUESTION,
        "oracle_draw": MyStates.ORACLE_DRAW,
        "global_cut": MyStates.GLOBAL_CUT,
        "waiting_reset_confirm": MyStates.WAITING_RESET_CONFIRM
    }

    target_state = state_map.get(step)
    if target_state:
        await bot.state_dispenser.set(vk_id, target_state, raw_json=state)
    else:
        try:
            await bot.state_dispenser.delete(vk_id)
        except KeyError:
            pass
        await set_fsm_state(vk_id, state)
    return True
