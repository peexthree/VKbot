import os
import aiohttp

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

async def add_user(vk_id: int):
    async with aiohttp.ClientSession() as session:
        # Пытаемся получить юзера
        async with session.get(f"{URL}/rest/v1/vk_ai_users?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            data = await r.json()
            if not data:
                # Если нет — создаем
                payload = {"vk_id": vk_id, "balance": 3}
                await session.post(f"{URL}/rest/v1/vk_ai_users", headers=HEADERS, json=payload)

async def get_balance(vk_id: int) -> int:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{URL}/rest/v1/vk_ai_users?vk_id=eq.{vk_id}", headers=HEADERS) as r:
            data = await r.json()
            return data[0]["balance"] if data else 0

async def decrease_balance(vk_id: int):
    current = await get_balance(vk_id)
    async with aiohttp.ClientSession() as session:
        payload = {"balance": current - 1}
        await session.patch(f"{URL}/rest/v1/vk_ai_users?vk_id=eq.{vk_id}", headers=HEADERS, json=payload)

async def init_db():
    # На REST API таблица должна быть уже создана через SQL Editor
    pass
