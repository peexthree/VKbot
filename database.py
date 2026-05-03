import os
import aiohttp
from typing import Optional, Dict, Any
import traceback

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
        session = aiohttp.ClientSession()

async def get_user(vk_id: int) -> Optional[Dict[str, Any]]:
    if not URL or not KEY:
        return None
    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                if data:
                    return data[0]
            else:
                print(f"Supabase error in get_user: {r.status} {await r.text()}")
            return None
    except Exception as e:
        print(f"Exception in get_user: {e}")
        traceback.print_exc()
        return None

async def get_all_subscribed_users() -> list[Dict[str, Any]]:
    """Получает список всех подписанных пользователей для утренних прогнозов"""
    if not URL or not KEY:
        return []
    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?has_full_chart=eq.true", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return data
            else:
                print(f"Supabase error in get_all_subscribed_users: {r.status} {await r.text()}")
            return []
    except Exception as e:
        print(f"Exception in get_all_subscribed_users: {e}")
        traceback.print_exc()
        return []

async def get_all_users() -> list[Dict[str, Any]]:
    """Получает список всех пользователей"""
    if not URL or not KEY:
        return []
    try:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return data
            else:
                print(f"Supabase error in get_all_users: {r.status} {await r.text()}")
            return []
    except Exception as e:
        print(f"Exception in get_all_users: {e}")
        traceback.print_exc()
        return []

async def get_inactive_free_users() -> list[Dict[str, Any]]:
    """Получает пользователей, которые не купили разбор, для кармических пушей"""
    if not URL or not KEY:
        return []
    try:
        # Для демо берем всех, кто не купил. В реальности нужно фильтровать по created_at < now - 3 days
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?has_full_chart=eq.false", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return data
            else:
                print(f"Supabase error in get_inactive_free_users: {r.status} {await r.text()}")
            return []
    except Exception as e:
        print(f"Exception in get_inactive_free_users: {e}")
        traceback.print_exc()
        return []

async def create_user(vk_id: int, birth_date: str, birth_time: str, birth_city: str) -> Optional[Dict[str, Any]]:
    if not URL or not KEY:
        return None
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
        "bonuses": 0,
        "last_active_date": None
    }
    try:
        async with session.post(f"{URL}/rest/v1/{TABLE_NAME}", headers=HEADERS, json=payload) as r:
            if r.status in (200, 201):
                data = await r.json()
                if data:
                    print("Записано в Users")
                    return data[0]
            else:
                print(f"Supabase error in create_user: {r.status} {await r.text()}")
            return None
    except Exception as e:
        print(f"Exception in create_user: {e}")
        traceback.print_exc()
        return None

async def update_user(vk_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not URL or not KEY:
        return None
    try:
        async with session.patch(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS, json=updates) as r:
            if r.status in (200, 204):
                data = await r.json()
                if data:
                    print("Записано в Users")
                    return data[0]
            else:
                print(f"Supabase error in update_user: {r.status} {await r.text()}")
            return None
    except Exception as e:
        print(f"Exception in update_user: {e}")
        traceback.print_exc()
        return None

async def get_user_state(vk_id: int) -> Optional[str]:
    if not URL or not KEY:
        return None
    try:
        async with session.get(f"{URL}/rest/v1/{FSM_TABLE}?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                if data:
                    return data[0].get("state", "")
            else:
                print(f"Supabase error in get_user_state: {r.status} {await r.text()}")
            return None
    except Exception as e:
        print(f"Exception in get_user_state: {e}")
        traceback.print_exc()
        return None

async def set_user_state(vk_id: int, state: str) -> bool:
    if not URL or not KEY:
        return False
    payload = {
        "vk_id": vk_id,
        "state": state
    }
    upsert_headers = HEADERS.copy()
    upsert_headers["Prefer"] = "resolution=merge-duplicates"
    try:
        async with session.post(f"{URL}/rest/v1/{FSM_TABLE}", headers=upsert_headers, json=payload) as r:
            if r.status in (200, 201, 204):
                print("Записано в FSM")
                return True
            else:
                print(f"Supabase error in set_user_state: {r.status} {await r.text()}")
                return False
    except Exception as e:
        print(f"Exception in set_user_state: {e}")
        traceback.print_exc()
        return False

