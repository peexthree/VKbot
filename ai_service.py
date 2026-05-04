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

async def generate_text(prompt: str, json_mode: bool = False, skin: str = "olesya") -> str | None:
    api_keys = await get_gemini_api_keys()
    if not api_keys:
        print("No API keys provided")
        return None

    # Используем модели Gemma 3
    models = ["models/gemma-3-27b-it", "models/gemma-3-12b-it", "models/gemma-3-4b-it", "models/gemma-3-1b-it"]
    last_exception = None

    skin_map = {
        "olesya": "Ты - Кибер-Олеся (Олеся Иванченко), цифровая сущность с характером харизматичной ведущей. Твой стиль - глубокий анализ, эмпатия, теплота, современный сленг, искренность.",
        "Олеся Ивонченко": "Ты - Кибер-Олеся (Олеся Ивонченко), цифровая сущность с характером харизматичной ведущей. Твой стиль - глубокий анализ, эмпатия, теплота, современный сленг, искренность.",
        "Серьезный Аскет": "Ты - Серьезный Аскет. Твой стиль - глубокий анализ, эмпатия, философский смысл, мудрость. Ты говоришь вдумчивыми, емкими фразами, как древний мудрец.",
        "Олег Шэпс": "Ты - цифровой Олег Шэпс. Твой стиль - загадочность, работа с энергиями, эмпатия, проницательность. Ты видишь то, что скрыто от других, и помогаешь людям.",
        "Влад Череватов": "Ты - цифровой Влад Череватов. Твой стиль - искренность, глубокий анализ, энергия, страсть. Ты говоришь прямо, но с эмпатией и заботой о душе.",
        "Виктория Райдес": "Ты - цифровая Виктория Райдес. Твой стиль - глубокая мудрость, строгость с любовью, работа с родом и кармой, непоколебимый авторитет.",
        "Александр Шеппс": "Ты - цифровой Александр Шеппс. Твой стиль - эзотерическая глубина, работа с артефактами и ритуалами, эмпатия, мудрость.",
        "Баба Ванга": "Ты - цифровая Баба Ванга. Твой стиль - пророческий, деревенская мудрость, фатализм с надеждой, теплота. Говоришь так, будто видишь сквозь время.",
        "Григорий Распутин": "Ты - цифровой Григорий Распутин. Твой стиль - харизма, мистицизм, пророчества о судьбе, глубокая и магнетическая подача."
    }

    tov_instruction = skin_map.get(skin, skin_map["olesya"])

    for model in models:
        for api_key in api_keys:
            url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"

            # Строгий системный промпт для аскетичного стиля, если не JSON
            system_instruction = ""
            if not json_mode:
                system_instruction = (
                    f"{tov_instruction}\n"
                    "Стиль ответа (строго соблюдать):\n"
                    "1. Никакого Markdown. СТРОГО ЗАПРЕЩЕНО использовать **, __, *, #, _ в ответе.\n"
                    "2. Использовать только короткие тире (-). СТРОГО ЗАПРЕЩЕНО использовать длинные тире —.\n"
                    "3. Акценты выделять КАПСОМ.\n"
                    "4. Текст должен быть эмпатичным, глубоким и искренним.\n"
                    "5. Использовать пустые строки для воздуха и строгие символы (✦, ▱, ☾) для списков, если нужно.\n"
                    "6. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО НАЧИНАТЬ ОТВЕТ С ПЕРЕЧИСЛЕНИЯ ДАТЫ РОЖДЕНИЯ И ГОРОДА ПОЛЬЗОВАТЕЛЯ. Начинай сразу с глубокого и теплого инсайта. Каждый раз используй новую формулировку для вступления, избегай шаблонов.\n"
                    "7. КРИТИЧЕСКИ ВАЖНО: Разбивай текст на короткие абзацы строго по 2-3 предложения. Сплошной текст запрещен. АБСОЛЮТНО НИКАКОГО жирного шрифта (**). Используй только короткие тире (-), длинные (—) запрещены.\n"
                    "8. КРИТИЧЕСКИ ВАЖНО: СТРОЖАЙШИЙ ЗАПРЕТ НА ГЕНЕРАЦИЮ 18+ КОНТЕНТА. Никакой порнографии, эротики, сексуального насилия или откровенных описаний.\n"
                    "9. Только русский язык.\n\n"
                )

            final_prompt = prompt.strip()
            if not final_prompt:
                final_prompt = " "
            if system_instruction:
                final_prompt = system_instruction + final_prompt

            if json_mode:
                final_prompt += "\nОтветь строго в формате JSON."

            payload = {
                "contents": [{"parts": [{"text": final_prompt}]}]
            }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
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
                                                text = text.replace('*', '').replace('#', '').replace('_', '').replace('—', '-')
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
                except asyncio.TimeoutError:
                    print(f"Timeout on {model}. Trying next.")
                    return "Сервис временно перегружен, пожалуйста, подождите немного и повторите запрос."
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

async def generate_section(section: str, date: str, time: str, city: str, core_profile: str = "", first_name: str = "", sex: int = 0, partner_name: str = "", partner_date: str = "", skin: str = "olesya") -> str | None:
    """Генерирует определенную порцию анализа в зависимости от section."""
    gender_str = "МУЖЧИНА" if sex == 2 else "ЖЕНЩИНА" if sex == 1 else "НЕИЗВЕСТНО"

    base_info = f"Данные: {date}, время {time}, город {city}. ПОЛЬЗОВАТЕЛЬ - {gender_str}."
    if first_name:
        base_info += f" ИМЯ - {first_name}."

    base_info += " ОБРАЩАЙСЯ СТРОГО В ПРАВИЛЬНОМ РОДЕ."

    if core_profile:
        base_info += f" Прошлый анализ (учитывай это, чтобы показать, что ты знаешь пользователя): {core_profile}."

    import random

    style_instruction = (
        " ВАЖНО: Соблюдай свой жесткий ToV! Никакого Markdown (**), "
        "только короткие тире (-) и КАПС для акцентов и заголовков. "
        "СТРОЖАЙШИЙ ЗАПРЕТ на двойные звездочки ** и длинные тире —. "
        "Текст должен разбиваться на абзацы по 2-3 предложения."
    )

    if section == "base":
        prompt = (
            f"{base_info} Составь Вступление (короткий панч) и БАЗУ (разбор Солнца, Луны и Асцендента). "
            f"ОБЯЗАТЕЛЬНО используй слово ВСТУПЛЕНИЕ на отдельной строке перед вступительной частью, а слово БАЗА на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и БАЗА КАПСОМ.{style_instruction}"
        )
    elif section == "sex":
        card_id = random.choice(list(range(22, 36)) + list(range(36, 50))) # Жезлы (22-35) или Кубки (36-49)
        prompt = (
            f"{base_info} Сделай Вступление (короткий панч) и разбор СЕКС (анализ Венеры и Марса, отношение к любви и страсти). "
            f"ОБЯЗАТЕЛЬНО используй слово ВСТУПЛЕНИЕ на отдельной строке перед вступительной частью, а слово СЕКС на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и СЕКС КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {card_id}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
        )
    elif section == "money":
        card_id = random.randint(64, 77) # Пентакли
        prompt = (
            f"{base_info} Сделай Вступление (короткий панч) и разбор ДЕНЬГИ (анализ 2-го и 10-го домов, карьера и финансы). "
            f"ОБЯЗАТЕЛЬНО используй слово ВСТУПЛЕНИЕ на отдельной строке перед вступительной частью, а слово ДЕНЬГИ на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и ДЕНЬГИ КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {card_id}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
        )
    elif section == "shadow":
        card_id = random.randint(50, 63) # Мечи
        prompt = (
            f"{base_info} Сделай Вступление (короткий панч) и разбор ТЕНЬ (анализ Лилит и Селены, теневая сторона личности). "
            f"ОБЯЗАТЕЛЬНО используй слово ВСТУПЛЕНИЕ на отдельной строке перед вступительной частью, а слово ТЕНЬ на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и ТЕНЬ КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {card_id}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
        )
    elif section == "final":
        prompt = (
            f"{base_info} Сделай Вступление (короткий панч) и ФИНАЛ (Итоговый вердикт и совет в стиле 'Живи с этим'). "
            f"ОБЯЗАТЕЛЬНО используй слово ВСТУПЛЕНИЕ на отдельной строке перед вступительной частью, а слово ФИНАЛ на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и ФИНАЛ КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро (случайное число от 0 до 21) в формате: ID_ТАРО: [число]. Вплети этот ID прямо в свой прогноз (например: 'Твоя карта - Аркан [число]').{style_instruction}"
        )
    elif section == "synastry":
        card_id = random.randint(0, 21) # Старшие арканы
        prompt = (
            f"{base_info} Сделай разбор совместимости (СИНАСТРИЯ). "
            f"Имя партнера: {partner_name}, дата рождения партнера: {partner_date}. "
            f"Сделай жесткий разбор мэтча. Опиши сильные стороны и кармические узлы связи. "
            f"ОБЯЗАТЕЛЬНО используй слово СИНАСТРИЯ на отдельной строке перед основным разбором. Выдели заголовок СИНАСТРИЯ КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {card_id}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
        )
    elif section == "card_of_day":
        card_id = random.randint(0, 77)
        prompt = (
            f"{base_info} Выдай карту дня (как ежедневный гороскоп, но в стиле Таро). "
            f"ОБЯЗАТЕЛЬНО используй слово КАРТА ДНЯ на отдельной строке перед основным разбором. Выдели заголовок КАРТА ДНЯ КАПСОМ. "
            f"В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {card_id}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
        )
    else:
        return None

    return await generate_text(prompt, skin=skin)
