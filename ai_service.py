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

    # Используем модели Gemma 3
    models = ["models/gemma-3-27b-it", "models/gemma-3-12b-it", "models/gemma-3-4b-it", "models/gemma-3-1b-it"]
    last_exception = None

    for model in models:
        for api_key in api_keys:
            url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"

            # Строгий системный промпт для аскетичного стиля, если не JSON
            system_instruction = ""
            if not json_mode:
                system_instruction = (
                    "Ты - Кибер-Олеся (Олеся Иванченко), цифровая сущность с характером ехидной и харизматичной ведущей. Твой стиль - интеллектуальная прожарка, жесткий сарказм, современный сленг, экспертность.\n"
                    "Стиль ответа (строго соблюдать):\n"
                    "1. Никакого Markdown. СТРОГО ЗАПРЕЩЕНО использовать **, __, *, #, _ в ответе.\n"
                    "2. Использовать только короткие тире (-). СТРОГО ЗАПРЕЩЕНО использовать длинные тире —.\n"
                    "3. Акценты выделять КАПСОМ.\n"
                    "4. Текст должен быть строгим, проницательным, с долей холодного интеллекта.\n"
                    "5. Использовать пустые строки для воздуха и строгие символы (✦, ▱, ☾) для списков, если нужно.\n\n"
                )

            final_prompt = prompt
            if system_instruction:
                final_prompt = system_instruction + final_prompt

            if json_mode:
                final_prompt += "\nОтветь строго в формате JSON."

            payload = {
                "contents": [{"parts": [{"text": final_prompt}]}]
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
                            error_text = await resp.text()
                            print(f"Text API Error status {resp.status} on {model}. Trying next key.")
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

async def generate_section(section: str, date: str, time: str, city: str, core_profile: str = "") -> str | None:
    """Генерирует определенную порцию анализа в зависимости от section."""
    base_info = f"Данные: {date}, время {time}, город {city}."
    if core_profile:
        base_info += f" Прошлый анализ (учитывай это, чтобы показать, что ты знаешь пользователя): {core_profile}."

    import random

    style_instruction = (
        " ВАЖНО: Соблюдай жесткий ToV Кибер-Олеси! Никакого Markdown (**), "
        "только короткие тире (-) и КАПС для акцентов и заголовков. "
        "СТРОЖАЙШИЙ ЗАПРЕТ на двойные звездочки ** и длинные тире —. "
        "Отвечай как ехидная, интеллектуальная ведущая с долей жесткого сарказма."
    )

    if section == "base":
        prompt = (
            f"{base_info} Составь Вступление (короткий панч) и БАЗУ (разбор Солнца, Луны и Асцендента). "
            f"Выдели заголовки ВСТУПЛЕНИЕ и БАЗА КАПСОМ.{style_instruction}"
        )
    elif section == "sex":
        card_id = random.choice(list(range(22, 36)) + list(range(36, 50))) # Жезлы (22-35) или Кубки (36-49)
        prompt = (
            f"{base_info} Сделай разбор СЕКС (анализ Венеры и Марса, отношение к любви и страсти). "
            f"Выдели заголовок СЕКС КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {card_id}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
        )
    elif section == "money":
        card_id = random.randint(64, 77) # Пентакли
        prompt = (
            f"{base_info} Сделай разбор ДЕНЬГИ (анализ 2-го и 10-го домов, карьера и финансы). "
            f"Выдели заголовок ДЕНЬГИ КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {card_id}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
        )
    elif section == "shadow":
        card_id = random.randint(50, 63) # Мечи
        prompt = (
            f"{base_info} Сделай разбор ТЕНЬ (анализ Лилит и Селены, теневая сторона личности). "
            f"Выдели заголовок ТЕНЬ КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {card_id}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
        )
    elif section == "final":
        prompt = (
            f"{base_info} Сделай ФИНАЛ (Итоговый вердикт и совет в стиле 'Живи с этим'). "
            f"Выдели заголовок ФИНАЛ КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро (случайное число от 0 до 21) в формате: ID_ТАРО: [число]. Вплети этот ID прямо в свой прогноз (например: 'Твоя карта - Аркан [число]').{style_instruction}"
        )
    else:
        return None

    return await generate_text(prompt)
