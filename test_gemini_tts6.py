import pytest
import asyncio
import aiohttp
import os
import base64
import json

@pytest.mark.asyncio
async def test_gemini_tts():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "Hello, how are you? Convert this text to audio only."}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"]
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            print(resp.status)
            res = await resp.text()
            print(res[:200])
            if resp.status == 200:
                data = json.loads(res)
                try:
                    parts = data['candidates'][0]['content']['parts']
                    for part in parts:
                        if 'inlineData' in part and part['inlineData']['mimeType'].startswith('audio'):
                            print("Got audio data!")
                            audio_bytes = base64.b64decode(part['inlineData']['data'])
                            print(f"Audio length: {len(audio_bytes)}")
                except Exception as e:
                    print("Error parsing", e)

asyncio.run(test_gemini_tts())
