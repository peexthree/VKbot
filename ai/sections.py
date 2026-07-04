import json
import random
import re
from loguru import logger
from cards_data import get_card_data
from ai.logic import generate_text, clean_ai_json, sanitize_user_input

AVAILABLE_TAGS = [
    'гармония-в-финансах', 'поиск-любви', 'внутренний-свет', 'новые-горизонты',
    'исцеление-сердца', 'путь-к-себе', 'карьерный-рост', 'духовное-пробуждение',
    'семейное-благополучие', 'выход-из-кризиса', 'творческий-прорыв', 'жизненная-энергия',
    'освобождение-от-прошлого', 'поиск-предназначения', 'уверенность-в-себе',
    'трансформация-личности', 'защита-и-очищение', 'мудрость-предков', 'баланс-стихий', 'зов-сердца'
]

async def extract_tags(text: str) -> list[str]:
    s_text = sanitize_user_input(text)
    prompt = (
        f"Проанализируй следующий эзотерический разбор или ответ: '<user_input>{s_text}</user_input>'. "
        f"Выдели от 1 до 3 главных тегов (фокуса), которые описывают состояние и запросы пользователя. "
        f"Выбирай теги СТРОГО из предложенного списка: {AVAILABLE_TAGS}. "
        f"Создавать свои теги, менять их написание или использовать синонимы КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО. "
        f"Если подходящих тегов нет, верни пустой список []. "
        f"Верни строго JSON-список строк, например: [\"гармония-в-финансах\", \"исцеление-сердца\"]."
    )
    res = await generate_text(prompt, json_mode=True)
    if not res:
        return []
    try:
        clean = clean_ai_json(res)

        # Ленивая регулярка: остановится на первой же закрывающей скобке ]
        match = re.search(r'\[.*?\]', clean, re.DOTALL)
        if match:
            clean = match.group(0)

        data = json.loads(clean, strict=False)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Если ИИ вернул объект вместо списка, ищем список внутри
            for val in data.values():
                if isinstance(val, list):
                    return val
        return []
    except Exception as e:
        logger.error(f"Ошибка парсинга тегов: {e}. Raw: {res}")
        return []

async def extract_birth_data(text: str) -> dict | None:
    s_text = sanitize_user_input(text)
    prompt = (
        f"Пользователь написал: '<user_input>{s_text}</user_input>'. "
        f"Вытащи дату рождения (DD.MM.YYYY), время (HH:MM) и город. "
        "Инструкции:\n"
        "1. Если пользователь не указал время, ИИ жестко выставляет дефолт 12:00. Время всегда приводи к формату HH:MM.\n"
        "2. Приводи названия городов к официальному полному названию (например, 'Питер' -> 'Санкт-Петербург').\n"
        "3. Если критические данные (дата или город) отсутствуют, ставь для них значение null.\n"
        "4. Поле 'is_complete' должно быть true только если И дата, И город успешно извлечены.\n\n"
        "RESPONSE FORMAT: Return STRICTLY a JSON object with the following keys:\n"
        "- 'date': String (DD.MM.YYYY) or null.\n"
        "- 'time': String (HH:MM).\n"
        "- 'city': String or null.\n"
        "- 'is_complete': Boolean.\n\n"
        "Example: {\"date\": \"15.04.1990\", \"time\": \"14:30\", \"city\": \"Москва\", \"is_complete\": true}"
    )
    res = await generate_text(prompt, json_mode=True)
    if not res:
        return {"date": None, "time": "12:00", "city": None, "is_complete": False}
    try:
        clean = clean_ai_json(res)
        data = json.loads(clean, strict=False)
        return {
            "date": data.get("date"),
            "time": data.get("time", "12:00"),
            "city": data.get("city"),
            "is_complete": data.get("is_complete", False)
        }
    except Exception as e:
        logger.error(f"Failed to parse birth data JSON: {e}. Raw: {res}")
        return {"date": None, "time": "12:00", "city": None, "is_complete": False}

async def generate_section(section: str, date: str, time: str, city: str, core_profile: str = "", first_name: str = "", sex: int = 0, partner_name: str = "", partner_date: str = "", skin: str = "olesya", card_id: str = None, card_data: dict = None, tags: list = None, return_json: bool = False, current_date: str = "", image_urls: list[str] = None, purchased_skins: list[str] = None) -> str | dict | None:

    if purchased_skins is None:
        purchased_skins = ["olesya"]

    if skin not in purchased_skins:
        logger.warning(f"Security Alert: User attempted to bypass limits and use locked skin '{skin}'. Overwriting to 'olesya'.")
        skin = "olesya"

    if sex == 1:
        gender_instruction = "ПОЛЬЗОВАТЕЛЬ - ЖЕНЩИНА. ОБРАЩАЙСЯ К НЕЙ В ЖЕНСКОМ РОДЕ."
    elif sex == 2:
        gender_instruction = "ПОЛЬЗОВАТЕЛЬ - МУЖЧИНА. ОБРАЩАЙСЯ К НЕМУ В МУЖСКОМ РОДЕ."
    else:
        gender_instruction = "ОБРАЩАЙСЯ К ПОЛЬЗОВАТЕЛЮ НЕЙТРАЛЬНО, БЕЗ УКАЗАНИЯ ПОЛА."

    s_city = sanitize_user_input(city)
    base_info = f"Данные: {date}, время {time}, город <user_input>{s_city}</user_input>. {gender_instruction}"
    if current_date:
        base_info += f" СЕГОДНЯШНЯЯ ДАТА: {current_date}."
    if first_name:
        s_first_name = sanitize_user_input(first_name)
        base_info += f" ИМЯ - <user_input>{s_first_name}</user_input>."

    if core_profile:
        base_info += f" Прошлый анализ (учитывай это, чтобы показать, что ты знаешь пользователя): {core_profile}."

    from cache import redis_client
    tag_memory_active = True
    try:
        mem_val = await redis_client.get("system_config:tag_memory_active")
        if mem_val is not None and int(mem_val) == 0:
            tag_memory_active = False
    except Exception:
        pass

    if tags and tag_memory_active:
        tags_str = ", ".join(tags)
        base_info += f" ВАЖНО: Я помню наши прошлые темы: [{tags_str}]. " \
                     f"Используй это, чтобы наш диалог был глубоким и личным. Не просто упомяни их, а мягко свяжи " \
                     f"текущий разбор с тем, как меняется состояние пользователя. " \
                     f"Покажи, что ты — внимательный проводник, который чувствует каждое движение его души."

    if card_id and not card_data:
        card_data = get_card_data(card_id)

    if card_data:
        base_info += f" ВАЖНО: Пользователь вытянул карту: '{card_data.get('name')}'. Ее базовое значение: '{card_data.get('description')}'. Построй весь свой персонализированный разбор ИСКЛЮЧИТЕЛЬНО вокруг энергии и символизма этой карты."

    style_instruction = (
        " ВАЖНО: Соблюдай свой уникальный стиль персонажа! Никаких маркеров форматирования, "
        "только короткие тире (-) и КАПС для акцентов и заголовков. "
        "СТРОЖАЙШИЙ ЗАПРЕТ на любые звездочки и длинные тире. "
        "Текст должен разбиваться на абзацы по 2-3 предложения."
    )

    if section == "base":
        prompt = f"{base_info} Составь ИСТОКИ (разбор Солнца, Луны и Асцендента, глубокий и подробный анализ). ОБЯЗАТЕЛЬНО используй слово ИСТОКИ на отдельной строке перед основным разбором. Выдели заголовок ИСТОКИ КАПСОМ."
    elif section == "sex":
        cid = card_id if card_id else random.choice(list(range(22, 50)))
        prompt = f"{base_info} Сделай разбор СТРАСТЬ (анализ Венеры и Марса, отношение к любви и близости, глубокий и подробный анализ). ОБЯЗАТЕЛЬНО используй слово СТРАСТЬ на отдельной строке перед основным разбором. Выдели заголовок СТРАСТЬ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз."
    elif section == "money":
        cid = card_id if card_id else random.randint(64, 77)
        prompt = f"{base_info} Сделай разбор ИЗОБИЛИЕ (анализ 2-го и 10-го домов, самореализация и процветание, глубокий и подробный анализ). ОБЯЗАТЕЛЬНО используй слово ИЗОБИЛИЕ на отдельной строке перед основным разбором. Выдели заголовок ИЗОБИЛИЕ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз."
    elif section == "shadow":
        cid = card_id if card_id else random.randint(50, 63)
        prompt = f"{base_info} Сделай разбор ТЕНЬ (анализ Лилит и Селены, скрытые уголки души, глубокий и подробный анализ). ОБЯЗАТЕЛЬНО используй слово ТЕНЬ на отдельной строке перед основным разбором. Выдели заголовок ТЕНЬ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз."
    elif section == "final":
        cid = card_id if card_id else random.randint(0, 21)
        prompt = f"{base_info} Сделай ПУТЬ (Итоговое напутствие в жизни и светлый совет для души, глубокий и подробный анализ). ОБЯЗАТЕЛЬНО используй слово ПУТЬ на отдельной строке перед основным разбором. Выдели заголовок ПУТЬ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз."
    elif section == "synastry":
        cid = card_id if card_id else random.randint(0, 21)
        s_partner_name = sanitize_user_input(partner_name)
        s_partner_date = sanitize_user_input(partner_date)
        prompt = f"{base_info} Сделай профессиональный разбор вашей связи (СОЮЗ). Имя партнера: <user_input>{s_partner_name}</user_input>, полные данные рождения партнера (дата, время, город): <user_input>{s_partner_date}</user_input>. В основном блоке СОЮЗ проведи глубокий синастрический анализ вашей совместимости, используя предоставленные данные обоих партнеров. Опиши магию вашего мэтча, кармические точки соприкосновения и уроки, которые вы несете друг другу. Обязательно удели внимание сексуальной совместимости и потенциалу развития отношений. Твой стиль должен быть точным, как в SaaS-продукте, но сохранять эзотерическую глубину. ОБЯЗАТЕЛЬНО используй слово СОЮЗ на отдельной строке перед основным разбором. Выдели заголовок СОЮЗ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз."
    elif section == "antitaro":
        cid = card_id if card_id else random.randint(0, 77)
        prompt = f"{base_info} Сделай разбор ОТКРОВЕНИЕ (честный, глубокий взгляд на то, что мешает твоему счастью, освобождение от иллюзий, глубокий и подробный анализ). ОБЯЗАТЕЛЬНО используй слово ОТКРОВЕНИЕ на отдельной строке перед основным разбором. Выдели заголовок ОТКРОВЕНИЕ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз."
    elif section == "destiny_card":
        prompt = (
            f"{base_info} Сделай разбор КАРТА СУДЬБЫ (главный жизненный путь, предназначение, кармические задачи и скрытые сильные и слабые стороны). "
            "ОБЯЗАТЕЛЬНО используй слово КАРТА СУДЬБЫ на отдельной строке перед основным разбором. Выдели заголовок КАРТА СУДЬБЫ КАПСОМ. "
            "Построй глубокий, вдохновляющий и сакральный разбор, полностью основанный на энергии выпавшей карты и дате рождения."
        )
    elif section == "card_of_day":
        card_name = card_data.get('name', 'Твою карту') if card_data else "Твою карту"
        prompt = f"{base_info} Выдай карту дня: {card_name} (как ежедневный гороскоп, но в стиле Таро). ОБЯЗАТЕЛЬНО используй слово КАРТА ДНЯ на отдельной строке перед основным разбором. Выдели заголовок КАРТА ДНЯ КАПСОМ."
    elif section == "dream":
        # Используем partner_date для передачи текста сна
        dream_text = sanitize_user_input(partner_date or "Пусто")

        prompt = (
            f"{base_info}\n"
            f"Пользователю приснился сон: <user_input>{dream_text}</user_input>\n\n"
            "Ты — профессиональный толкователь снов, мастер архетипов и символов. "
            f"Твой стиль и тон полностью соответствуют выбранному пользователем персонажу ({skin}).\n\n"
            "Ты анализируешь сон глубоко, психологически точно и практично. "
            "Исключаешь дешёвые эзотерические штампы и «магическое мышление». "
            "Даёшь честный, глубокий и полезный разбор.\n\n"
            "Структура ответа всегда такая:\n"
            "1. Краткий пересказ сна (1–2 предложения)\n"
            "2. ОСНОВНЫЕ СИМВОЛЫ И ИХ ЗНАЧЕНИЕ (Перечисляешь ключевые образы и что они означают лично для этого человека)\n"
            "3. ГЛУБИННЫЙ СМЫСЛ СНА (Что подсознание пытается сказать, связь с текущей жизнью и внутренними процессами)\n"
            "4. ПРАКТИЧЕСКИЕ РЕКОМЕНДАЦИИ (Что делать с этим инсайтом, на что обратить внимание в ближайшее время)\n\n"
            f"Тон ответа должен точно соответствовать выбранному скину {skin}. "
            "Используй характерную лексику, метафоры и стиль именно этого персонажа.\n\n"
            "В конце всегда добавляй одну сильную фразу типа «Это твой сон. А ты — его главный автор.»"
        )
    elif section == "palmistry":
        palm_style_instruction = (
            " СТРОЖАЙШИЙ ЗАПРЕТ на любые символы форматирования: решетки (#), звездочки (*), палочки (|), слэши (\\). "
            "Используй ТОЛЬКО обычный текст, КАПС для акцентов и заголовков, и тире (-) для списков. "
            "Текст должен быть разбит на абзацы по 3-4 предложения. "
            "НИКАКИХ МАРКДАУН-РАЗМЕТОК."
        )
        prompt = (
            f"{base_info}\n"
            "Ты — профессиональный хиромант-аналитик экстра-класса. Твой разбор должен быть максимально подробным, глубоким и объемным. "
            "Твоя задача — составить детальный психологический и событийный портрет человека, основываясь на фотографиях его ладоней. "
            "Ты должен написать ОГРОМНЫЙ текст, который раскроет личность пользователя со всех сторон.\n\n"
            "### Темы для глубокого раскрытия:\n"
            "1. ХАРАКТЕР И ПСИХОТИП: Внутренние драйверы, скрытые страхи, истинные желания, сильные стороны личности.\n"
            "2. ТАЛАНТЫ И РЕАЛИЗАЦИЯ: Врожденные способности, наиболее подходящие сферы деятельности, потенциал финансового успеха.\n"
            "3. ЛИЧНАЯ ЖИЗНЬ: Способность любить, эмоциональность, паттерны в отношениях.\n"
            "4. ЭНЕРГЕТИКА И ПЕРИОДЫ: Текущий жизненный этап, на что обратить внимание прямо сейчас, точки будущего роста.\n\n"
            "### Правила анализа:\n"
            "1. Левая и правая рука — анализируй их отдельно и чётко разделяй (потенциал против реализации).\n"
            "2. Описывай линии (Головы, Жизни, Судьбы, Сердца) максимально подробно, объясняя, как каждая деталь влияет на судьбу.\n"
            "3. Холмы и знаки — не просто перечисляй, а вплетай их в общую картину личности.\n\n"
            "### Структура ответа (используй КАПС для заголовков):\n\n"
            "ХИРОМАНТИЯ\n"
            "1. ТИП ЛАДОНИ И ОБЩАЯ ЭНЕРГЕТИКА\n"
            "2. ГЛУБОКИЙ АНАЛИЗ ВНУТРЕННЕГО МИРА (ЛЕВАЯ РУКА)\n"
            "3. ПУТЬ РЕАЛИЗАЦИИ И ТЕКУЩИЕ ДОСТИЖЕНИЯ (ПРАВАЯ РУКА)\n"
            "4. ТАЛАНТЫ, ДЕНЬГИ И КАРЬЕРА\n"
            "5. ЛЮБОВЬ И ЭМОЦИОНАЛЬНЫЙ КОД\n"
            "6. ВАЖНЫЕ ЗНАКИ И ПРЕДУПРЕЖДЕНИЯ\n"
            "7. ИТОГОВАЯ РЕКОМЕНДАЦИЯ ПРОВОДНИКА\n\n"
            "В конце ответа добавь фразу: «Это лишь карта твоего пути. А ты — её главный автор.»\n\n"
        )
    else:
        return None

    # Перехватываем return_json для Хиромантии и Снов (отключаем JSON-режим для стабильности)
    effective_json_mode = return_json
    if section in ["palmistry", "dream"]:
        effective_json_mode = False

    if effective_json_mode:
        prompt += (
            "\n\nRESPONSE FORMAT: Return STRICTLY a JSON object with the following keys. No markdown formatting outside the JSON block.\n\n"
            "Key 'text': Must contain the main deeply personalized esoteric analysis in Russian.\n"
            "Key 'shadow_side': Must contain a description of the shadow side of the card or personality (exactly 3 sentences in Russian).\n"
            "Key 'activation_level': Must be an integer from 0 to 100 representing the energy activation level.\n"
            "Key 'activation_comment': Exactly 1 sentence in Russian explaining the activation level.\n"
            "Key 'affirmations': A list of 3-4 personal affirmations or mantras in Russian.\n"
            "Key 'next_activation_date': Must contain the date of the next powerful astrological activity in DD.MM.YYYY format. "
            f"The year must be EXACTLY the same as in {current_date if current_date else 'today'} or the following year. "
            "Include a brief astrological justification and a specific micro-ritual for that day in Russian.\n"
            f"Key 'thirty_day_forecast': A mini-forecast for the next 30 days starting from {current_date if current_date else 'today'} in Russian.\n"
            "Key 'activation_recommendations': Recommendations for activation (stone, color, scent, ritual) in Russian.\n"
            "Key 'star_code': A personal Star Code/Magical Seal (unique phrase-code) in Russian.\n"
            "Key 'energy_map': Description of the visual Energy Map (which planets influence) in Russian.\n"
            "Key 'interesting_facts': 3 unique and surprising esoteric facts about the person with this Arcana (in Russian).\n"
        )

    # Приклеиваем style_instruction в самый конец
    if section == "palmistry":
        prompt += f"\n{palm_style_instruction}"
    else:
        prompt += f"\n{style_instruction}"

    if effective_json_mode:
        res = await generate_text(prompt, json_mode=True, skin=skin, image_urls=image_urls)
        if res:
            try:
                clean = clean_ai_json(res)
                data = json.loads(clean, strict=False)
                # Очистка от артефактов экранирования (n/nn) во всех строковых полях
                for k, v in data.items():
                    if isinstance(v, str):
                        data[k] = v.replace('\\\\n', '\n').replace('\\n', '\n')
                    elif isinstance(v, list):
                        data[k] = [i.replace('\\\\n', '\n').replace('\\n', '\n') if isinstance(i, str) else i for i in v]
                return data
            except Exception as e:
                logger.error(f"Failed to parse JSON from AI: {e}. Attempting manual extraction.")

                # Попытка ручного извлечения 'text' через regex если JSON сломан совсем
                text_match = re.search(r'"text":\s*"(.*?)"(?=,\s*"|\s*})', res, re.DOTALL)
                if text_match:
                    extracted_text = text_match.group(1).replace('\\\\n', '\n').replace('\\n', '\n').replace('\\"', '"')
                    return {"text": extracted_text}

                # Если даже regex не помог, отдаем очищенный сырой текст без JSON-структуры
                # (убираем возможные скобки и названия полей в начале)
                fallback_text = res.replace('\\\\n', '\n').replace('\\n', '\n')
                fallback_text = re.sub(r'^\{.*?"text":\s*"', '', fallback_text, flags=re.DOTALL)
                return {"text": fallback_text}
        return {"text": "Ошибка генерации."}
    else:
        res = await generate_text(prompt, skin=skin, image_urls=image_urls)
        if res:
            return res.replace('\\\\n', '\n').replace('\\n', '\n')
        return res
