import pytest
import asyncio
import aiohttp
import os
import base64

@pytest.mark.asyncio
async def test_gemini_tts():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "Hello, say hello world and output audio."}]}],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            print(resp.status)
            print(await resp.text())

asyncio.run(test_gemini_tts())
