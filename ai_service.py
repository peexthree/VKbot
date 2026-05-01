import os
import aiohttp
import base64

async def get_gemini_api_keys() -> list[str]:
    api_keys_str = os.environ.get('GEMINI_API_KEYS', '')
    if not api_keys_str:
        api_keys_str = os.environ.get('GEMINI_API_KEY', '')
    keys = [k.strip() for k in api_keys_str.split(',') if k.strip()]
    return keys

async def generate_text(prompt: str) -> str | None:
    api_keys = await get_gemini_api_keys()
    if not api_keys:
        print("No API keys provided")
        return None

    last_exception = None
    for api_key in api_keys:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        res_data = await resp.json()
                        try:
                            return res_data['candidates'][0]['content']['parts'][0]['text']
                        except (KeyError, IndexError):
                            return "Не удалось сгенерировать текст."
                    elif resp.status == 429:
                        print(f"Rate limit hit for text generation. Rotating...")
                        continue
                    else:
                        print(f"Text API Error status {resp.status}. Trying next key.")
                        error_text = await resp.text()
                        print(f"Error details: {error_text}")
                        continue
            except Exception as e:
                last_exception = e
                print(f"API Error: {e}. Trying next key if available.")
                continue

    print(f"All keys exhausted or failed for text generation. Last error: {last_exception}")
    return None

async def generate_image(prompt: str) -> bytes | None:
    api_keys = await get_gemini_api_keys()
    if not api_keys:
        print("No API keys provided")
        return None

    last_exception = None
    for api_key in api_keys:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={api_key}"
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1}
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        res_data = await resp.json()
                        try:
                            output_b64 = res_data['predictions'][0]['bytesBase64Encoded']
                            return base64.b64decode(output_b64)
                        except (KeyError, IndexError):
                            return None
                    elif resp.status == 429:
                        print(f"Rate limit hit for image generation. Rotating...")
                        continue
                    else:
                        print(f"Image API Error status {resp.status}. Trying next key.")
                        error_text = await resp.text()
                        print(f"Error details: {error_text}")
                        continue
            except Exception as e:
                last_exception = e
                print(f"API Error: {e}. Trying next key if available.")
                continue

    print(f"All keys exhausted or failed for image generation. Last error: {last_exception}")
    return None
