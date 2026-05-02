import asyncio
import aiohttp
import os

async def list_models():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            for model in data.get("models", []):
                print(model.get("name"))

asyncio.run(list_models())
