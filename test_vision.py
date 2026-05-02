import asyncio
import aiohttp
import os
import base64

async def test_vision(url_image: str):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    # Wait, the instruction mentions "Физиогномика (Gemini Vision): Анализ совместимости по фото партнера через нейросетевое зрение."
    pass
