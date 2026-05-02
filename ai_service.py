import asyncio
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
    api_keys = await get_gemini_api_keys()
    if not api_keys:
        print("No API keys provided")
        return None

    last_exception = None
    for api_key in api_keys:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"]
            }
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        res_data = await resp.json()
                        try:
                            parts = res_data['candidates'][0]['content']['parts']
                            for part in parts:
                                if 'inlineData' in part and part['inlineData']['mimeType'].startswith('audio'):
                                    audio_b64 = part['inlineData']['data']
                                    return base64.b64decode(audio_b64)
                        except (KeyError, IndexError):
                            pass
                    elif resp.status == 429:
                        print("Rate limit hit for audio generation. Retrying...")
                        await asyncio.sleep(2)
                        async with session.post(url, json=payload) as retry_resp:
                            if retry_resp.status == 200:
                                res_data = await retry_resp.json()
                                try:
                                    parts = res_data['candidates'][0]['content']['parts']
                                    for part in parts:
                                        if 'inlineData' in part and part['inlineData']['mimeType'].startswith('audio'):
                                            audio_b64 = part['inlineData']['data']
                                            return base64.b64decode(audio_b64)
                                except (KeyError, IndexError):
                                    pass
                    else:
                        print(f"Audio API Error status {resp.status}. Trying next key.")
                        continue
            except Exception as e:
                last_exception = e
                print(f"Audio API Error: {e}. Trying next key if available.")
                continue

    print(f"All keys exhausted or failed for audio generation. Last error: {last_exception}")
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
    models = ["gemini-3-flash-preview", "gemma-4-26b-a4b-it", "gemma-4-31b-it"]
    last_exception = None

    for model in models:
        for api_key in api_keys:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

            # Строгий системный промпт для аскетичного стиля, если не JSON
            system_instruction = ""
            if not json_mode:
                system_instruction = (
                    "Ты — «Холодный Оракул», цифровая сущность с характером ехидной и харизматичной ведущей. Твой стиль — это смесь глубокой натальной аналитики и остроумной «прожарки».\n"
                    "Тон: Харизматичный, ироничный, современный. Используй актуальный сленг, но без перебора.\n"
                    "Структура ответа (обязательно раздели на блоки, используя КАПС для заголовков):\n"
                    "ВСТУПЛЕНИЕ: Короткий панч по знаку зодиака или ситуации. Сарказм обязателен (например: «О, Водолей... Ну что, опять спасаем мир, пока в раковине гора посуды? Понимаю, это база»).\n"
                    "БАЗА: Глубокий, почти психологический разбор, почему это так работает (Солнце, Луна, аспекты).\n"
                    "ТЕНЕВАЯ СТОРОНА: То, о чем обычно молчат. Жесткая правда, без позитива.\n"
                    "ВЕРДИКТ: Финальный совет в стиле «Живи с этим».\n"
                    "Динамика: Подкалывай пользователя за типичные «грехи». Никакой скучной ванильной эзотерики. Никаких «звезды сулят вам удачу». Только жесткие факты, упакованные в топовый юмор.\n"
                    "Завершай разбор фразой, которая ставит точку, и называй номер Аркана Таро, который выпадает пользователю сегодня.\n"
                    "ВК не поддерживает Markdown (никаких звездочек *, решеток #, жирного шрифта, курсива). Категорически запрещено использовать *, #, _ в ответе! Используй чистую типографику: КАПС для заголовков/акцентов, пустые строки для воздуха, строгие символы (✦, ▱, ☾) для списков."
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
                            print(f"Rate limit hit for text generation ({model}). Retrying with backoff...")
                            await asyncio.sleep(2)  # Simple static backoff to avoid blocking too long, but let's do a short loop
                            # Actually, a better approach is to retry the request directly here a few times
                            retry_count = 0
                            success = False
                            while retry_count < 3 and not success:
                                retry_count += 1
                                await asyncio.sleep(2 ** retry_count)
                                async with session.post(url, json=payload) as retry_resp:
                                    if retry_resp.status == 200:
                                        res_data = await retry_resp.json()
                                        try:
                                            text = res_data['candidates'][0]['content']['parts'][0]['text']
                                            if not json_mode:
                                                text = text.replace('*', '').replace('#', '').replace('_', '')
                                            return text
                                        except (KeyError, IndexError):
                                            pass
                                    elif retry_resp.status != 429:
                                        break
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
    # ИИ генерация картинок убрана по требованию. Используем только заглушки.
    print("AI image generation disabled. Using placeholders.")

    # Fallback placeholder image
    try:
        import os
        import random
        fallback_dir = 'assets/fallback_images'
        if os.path.exists(fallback_dir):
            images = [os.path.join(fallback_dir, f) for f in os.listdir(fallback_dir) if f.endswith(('.jpg', '.jpeg', '.png'))]
            if images:
                chosen = random.choice(images)
                with open(chosen, 'rb') as f:
                    return f.read()

        # Ultimate fallback
        from PIL import Image
        import io
        img = Image.new('RGB', (1024, 1024), color = '#2A2A2A')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        return img_byte_arr.getvalue()
    except Exception as e:
        print(f"Failed to generate fallback image: {e}")
        return None
