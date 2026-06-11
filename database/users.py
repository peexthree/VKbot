import datetime
from typing import Any, Dict
from loguru import logger
from database.config import URL, KEY, HEADERS, TABLE_NAME
import database.core as core

async def create_user(vk_id: int, first_name: str = ""):
    if not URL or not KEY or core.session is None: return None
    payload = {
        "vk_id": vk_id, "first_name": first_name, "is_registered": True,
        "free_teaser_used": False, "is_subscribed": False, "compatibility_balance": 0, "core_profile": "",
        "partners": [], "free_card_used": False,
        "purchased_sections": {"sex": False, "money": False, "shadow": False, "final": False, "sex_val": 0, "first_name": first_name, "oracle_access": False, "card_of_day_last_used": None, "conversion_step": "started"},
        "has_full_chart": False, "forecast_time": None, "balance": 0, "oracle_last_used": None,
        "has_priority_access": False, "bonuses": None, "last_active_date": datetime.datetime.now(datetime.timezone.utc).isoformat(), "active_skin": "olesya",
        "purchased_skins": ["olesya"], "transit_trial_days": 0, "transit_sub_expires_at": None, "unlocked_cards": {},
        "weekly_log": [], "visit_streak": 0, "total_cards_received": 0, "last_daily_bonus_date": None,
        "welcome_bonus_received": False, "tags": [], "latest_reading_text": None, "latest_reading_data": {},
        "readings_history": [],
        "used_skins_count": 0, "compatibility_partners_count": 0, "compatibility_partners_hashes": [],
        "dreams_analyzed_count": 0, "rituals_count": 0, "active_referrals_count": 0, "level_3_counted": False
    }
    headers = HEADERS.copy()
    headers["Prefer"] = "return=representation"
    try:
        async with core.session.post(f"{URL}/rest/v1/{TABLE_NAME}", headers=headers, json=payload) as r:
            if r.status in (200, 201):
                data = await r.json()
                if data:
                    logger.success(f"✅ Создан пользователь vk_id={vk_id}")
                    return data[0]
    except Exception as e: logger.error(f"Ошибка в create_user: {e}")
    return None

async def update_user(vk_id: int, updates: Dict[str, Any]):
    if not URL or not KEY or core.session is None: return None
    headers = HEADERS.copy()
    headers["Prefer"] = "return=representation"
    try:
        async with core.session.patch(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=headers, json=updates) as r:
            if r.status in (200, 204):
                data = await r.json()
                if data: return data[0]
    except Exception as e: logger.error(f"Ошибка в update_user: {e}")
    return None

async def delete_user(vk_id: int):
    if not URL or not KEY or core.session is None: return False
    try:
        async with core.session.delete(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            return r.status in (200, 204)
    except Exception as e: logger.error(f"Ошибка в delete_user: {e}")
    return False

async def get_user_count():
    if not URL or not KEY or core.session is None: return 0
    headers = HEADERS.copy()
    headers["Prefer"] = "count=exact"
    try:
        async with core.session.get(f"{URL}/rest/v1/{TABLE_NAME}?select=vk_id&limit=1", headers=headers) as r:
            if r.status in (200, 206):
                content_range = r.headers.get("Content-Range", "")
                if "/" in content_range:
                    return int(content_range.split("/")[-1])
    except Exception as e: logger.error(f"Error in get_user_count: {e}")
    return 0

async def get_users_paginated(limit: int = 10, offset: int = 0):
    if not URL or not KEY or core.session is None: return []
    headers = HEADERS.copy()
    headers["Range"] = f"{offset}-{offset + limit - 1}"
    try:
        async with core.session.get(f"{URL}/rest/v1/{TABLE_NAME}?select=*&order=created_at.desc", headers=headers) as r:
            if r.status in (200, 206):
                return await r.json()
    except Exception as e: logger.error(f"Error in get_users_paginated: {e}")
    return []

async def add_energy(vk_id: int, energy: int):
    """Добавляет энергию пользователю (атомарно через RPC)"""
    from database.core import call_rpc
    result = await call_rpc("increment_user_balance", {"p_vk_id": vk_id, "p_amount": energy})
    if result:
        logger.success(f"✅ Атомарно начислено {energy} энергии пользователю vk_id={vk_id}")
        return True
    return False
