import os
import asyncio
from supabase import create_async_client, AsyncClient

url: str = os.environ.get("SUPABASE_URL", "")
key: str = os.environ.get("SUPABASE_KEY", "")

_client: AsyncClient | None = None

async def get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await create_async_client(url, key)
    return _client

async def add_user(vk_id: int):
    client = await get_client()
    # Check if user exists
    response = await client.table("vk_ai_users").select("*").eq("vk_id", vk_id).execute()
    if not response.data:
        # User does not exist, add with default balance 3
        await client.table("vk_ai_users").insert({"vk_id": vk_id, "balance": 3}).execute()

async def get_balance(vk_id: int) -> int:
    client = await get_client()
    response = await client.table("vk_ai_users").select("balance").eq("vk_id", vk_id).execute()
    if response.data:
        return response.data[0]["balance"]
    return 0

async def decrease_balance(vk_id: int):
    client = await get_client()
    # First get the current balance
    current_balance = await get_balance(vk_id)
    if current_balance > 0:
        new_balance = current_balance - 1
        await client.table("vk_ai_users").update({"balance": new_balance}).eq("vk_id", vk_id).execute()
