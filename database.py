import os
import aiohttp
from typing import Optional, Dict, Any

URL = os.environ.get("SUPABASE_URL", "")
KEY = os.environ.get("SUPABASE_KEY", "")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}
TABLE_NAME = "vk_esoteric_users"

async def get_user(vk_id: int) -> Optional[Dict[str, Any]]:
    if not URL or not KEY:
        return None
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                if data:
                    return data[0]
            return None

async def get_all_subscribed_users() -> list[Dict[str, Any]]:
    """Получает список всех подписанных пользователей для утренних прогнозов"""
    if not URL or not KEY:
        return []
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?is_subscribed=eq.true", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return data
            return []

async def get_inactive_free_users() -> list[Dict[str, Any]]:
    """Получает пользователей, которые не купили разбор, для кармических пушей"""
    if not URL or not KEY:
        return []
    async with aiohttp.ClientSession() as session:
        # Для демо берем всех, кто не купил. В реальности нужно фильтровать по created_at < now - 3 days
        async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?has_full_chart=eq.false", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return data
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
        "current_step": "",
        "has_full_chart": False,
        "free_card_used": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{URL}/rest/v1/{TABLE_NAME}", headers=HEADERS, json=payload) as r:
            if r.status in (200, 201):
                data = await r.json()
                if data:
                    return data[0]
            return None

async def update_user(vk_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not URL or not KEY:
        return None
    async with aiohttp.ClientSession() as session:
        async with session.patch(f"{URL}/rest/v1/{TABLE_NAME}?vk_id=eq.{vk_id}", headers=HEADERS, json=updates) as r:
            if r.status in (200, 204):
                data = await r.json()
                if data:
                    return data[0]
            return None

async def init_db():
    pass
