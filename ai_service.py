import os
import aiohttp
import base64

async def get_gemini_api_keys() -> list[str]:
    api_keys_str = os.environ.get('GEMINI_API_KEYS', '')
    if not api_keys_str:
        api_keys_str = os.environ.get('GEMINI_API_KEY', '')
    keys = [k.strip() for k in api_keys_str.split(',') if k.strip()]
    return keys

import json
import re

async def generate_audio_prediction(text: str) -> bytes | None:
    # Имитация генерации голоса (ElevenLabs/Edge-TTS).
    # Для реального проекта здесь будет aiohttp запрос к API генерации речи.
    # Сейчас мы возвращаем заглушку, чтобы не усложнять зависимости
    return b"dummy_audio_data"

async def generate_text(prompt: str, json_mode: bool = False) -> str | None:
    api_keys = await get_gemini_api_keys()
    if not api_keys:
        print("No API keys provided")
        return None

    # Пожелание клиента: перебор моделей.
    # Так как мы используем REST API Google, мы будем менять URL на разные версии Gemini,
    # если 2.5-flash недоступна. (Gemma через REST API Google не всегда стабильна, но
    # можно добавить fallback на gemini-1.5-pro или gemini-1.5-flash).
    models = ["gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    last_exception = None

    for model in models:
        for api_key in api_keys:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

            # Строгий системный промпт для аскетичного стиля, если не JSON
            system_instruction = ""
            if not json_mode:
                system_instruction = (
                    "Ты оракул-аскет. Твой тон: отстраненный, уважительный, с холодным достоинством. "
                    "ВК не поддерживает Markdown (никаких звездочек *, решеток #, жирного шрифта, курсива). "
                    "Категорически запрещено использовать *, #, _ в ответе! "
                    "Используй чистую типографику: КАПС для заголовков/акцентов, пустые строки для воздуха, "
                    "строгие символы (✦, ▱, ☾) для списков."
                )

            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }

            if system_instruction:
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction}]
                }

            if json_mode:
                payload["generationConfig"] = {
                    "responseMimeType": "application/json"
                }

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            res_data = await resp.json()
                            try:
                                text = res_data['candidates'][0]['content']['parts'][0]['text']
                                # Принудительная очистка от мусора из нулевых
                                if not json_mode:
                                    text = text.replace('*', '').replace('#', '').replace('_', '')
                                    # Заменяем markdown заголовки на КАПС если нейросеть всё равно их выдала
                                    # (но без #, так как мы их удалили. Проще просто почистить).
                                return text
                            except (KeyError, IndexError):
                                continue
                        elif resp.status == 429:
                            print(f"Rate limit hit for text generation ({model}). Rotating key...")
                            continue
                        else:
                            print(f"Text API Error status {resp.status} on {model}. Trying next key.")
                            error_text = await resp.text()
                            print(f"Error details: {error_text}")
                            continue
                except Exception as e:
                    last_exception = e
                    print(f"API Error ({model}): {e}. Trying next.")
                    continue

    print(f"All keys and models exhausted or failed for text generation. Last error: {last_exception}")
    return None

async def extract_birth_data(text: str) -> dict | None:
    """Извлекает дату, время и город из свободного текста."""
    prompt = (
        f"Пользователь написал следующий текст: '{text}'. "
        f"Вытащи из него дату рождения (формат DD.MM.YYYY), время рождения (формат HH:MM, если не указано - '12:00') "
        f"и город рождения. Верни строго JSON вида: "
        f"{{\"date\": \"15.04.1990\", \"time\": \"14:30\", \"city\": \"Москва\"}}. "
        f"Если дату или город невозможно определить, верни пустые строки для них."
    )
    res = await generate_text(prompt, json_mode=True)
    if not res:
        return None
    try:
        # Иногда модель оборачивает JSON в markdown блоки, хотя мы просим application/json
        clean_res = re.sub(r'```json\n|\n```|```', '', res).strip()
        data = json.loads(clean_res)
        return data
    except json.JSONDecodeError:
        print(f"Failed to decode JSON from extraction: {res}")
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

    # Fallback placeholder image (a simple generated solid dark gold/grey image to prevent UI breaks)
    try:
        from PIL import Image
        import io
        img = Image.new('RGB', (1024, 1024), color = '#2A2A2A')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        return img_byte_arr.getvalue()
    except Exception as e:
        print(f"Failed to generate fallback image: {e}")
        return None
