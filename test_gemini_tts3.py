import asyncio
import aiohttp
import os
import base64

async def test_gemini_tts():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "Hello, how are you?"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"]
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            print(resp.status)
            res = await resp.text()
            print(res[:200])

asyncio.run(test_gemini_tts())
