import json
import random
from loguru import logger
from cards_data import get_card_data
from ai.logic import generate_text, clean_ai_json

async def extract_tags(text: str) -> list[str]:
    prompt = (
        f"Проанализируй следующий эзотерический разбор или ответ: '{text}'. "
        f"Выдели 1-3 главных жестких тега (болей/фокусов), которые описывают текущую ситуацию пользователя. "
        f"Примеры тегов: 'фокус-на-деньгах', 'кризис-отношений', 'выгорание', 'поиск-себя', 'карьерный-тупик', 'одиночество'. "
        f"Верни строго JSON-список строк, например: [\"фокус-на-деньгах\", \"кризис-отношений\"]."
    )
    res = await generate_text(prompt, json_mode=True)
    if not res:
        return []
    try:
        clean = clean_ai_json(res)
        tags = json.loads(clean)
        return tags if isinstance(tags, list) else []
    except Exception as e:
        logger.error(f"Ошибка парсинга тегов: {e}. Raw: {res[:200]}...")
        return []

async def extract_birth_data(text: str) -> dict | None:
    prompt = (
        f"Пользователь написал: '{text}'. "
        f"Вытащи дату рождения (DD.MM.YYYY), время (HH:MM) и город. "
        f"Если пользователь не указал время, по умолчанию ставь 12:00. Время всегда приводи к формату HH:MM. "
        f"Верни строго JSON: {{\"date\": \"15.04.1990\", \"time\": \"14:30\", \"city\": \"Москва\"}}."
    )
    res = await generate_text(prompt, json_mode=True)
    if not res:
        return None
    try:
        clean = clean_ai_json(res)
        return json.loads(clean)
    except Exception as e:
        logger.error(f"Failed to parse birth data JSON: {e}. Raw: {res[:200]}...")
        return None

async def generate_section(section: str, date: str, time: str, city: str, core_profile: str = "", first_name: str = "", sex: int = 0, partner_name: str = "", partner_date: str = "", skin: str = "olesya", card_id: str = None, card_data: dict = None, tags: list = None, return_json: bool = False) -> str | dict | None:

    gender_str = "МУЖЧИНА" if sex == 2 else "ЖЕНЩИНА" if sex == 1 else "НЕИЗВЕСТНО"

    base_info = f"Данные: {date}, время {time}, город {city}. ПОЛЬЗОВАТЕЛЬ - {gender_str}."
    if first_name:
        base_info += f" ИМЯ - {first_name}."

    base_info += " ОБРАЩАЙСЯ СТРОГО В ПРАВИЛЬНОМ РОДЕ. ОБЯЗАТЕЛЬНО используй слово ВСТУПЛЕНИЕ на отдельной строке перед вступительной частью."

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
        base_info += f" ВАЖНО: В памяти Синдиката сохранились прошлые фокусы пользователя: [{tags_str}]. " \
                     f"Используй это, чтобы создать ощущение непрерывного диалога. Не просто упомяни их, а свяжи " \
                     f"текущий разбор (новую карту) с тем, как прогрессирует ситуация пользователя по этим темам. " \
                     f"Покажи, что ты — его личный проводник, который следит за его путем."

    if card_id and not card_data:
        card_data = get_card_data(card_id)

    if card_data:
        base_info += f" ВАЖНО: Пользователь вытянул карту: '{card_data.get('name')}'. Ее базовое значение: '{card_data.get('description')}'. Построй весь свой персонализированный разбор ИСКЛЮЧИТЕЛЬНО вокруг энергии и символизма этой карты."

    style_instruction = (
        " ВАЖНО: Соблюдай свой жесткий ToV! Никаких маркеров форматирования, "
        "только короткие тире (-) и КАПС для акцентов и заголовков. "
        "СТРОЖАЙШИЙ ЗАПРЕТ на любые звездочки и длинные тире. "
        "Текст должен разбиваться на абзацы по 2-3 предложения."
    )

    if section == "base":
        prompt = f"{base_info} Составь Вступление (короткий панч) и БАЗА (разбор Солнца, Луны и Асцендента). ОБЯЗАТЕЛЬНО используй слово БАЗА на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и БАЗА КАПСОМ.{style_instruction}"
    elif section == "sex":
        cid = card_id if card_id else random.choice(list(range(22, 50)))
        prompt = f"{base_info} Сделай Вступление (короткий панч) и разбор СЕКС (анализ Венеры и Марса, отношение к любви и страсти). ОБЯЗАТЕЛЬНО используй слово СЕКС на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и СЕКС КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
    elif section == "money":
        cid = card_id if card_id else random.randint(64, 77)
        prompt = f"{base_info} Сделай Вступление (короткий панч) и разбор ДЕНЬГИ (анализ 2-го и 10-го домов, карьера и финансы). ОБЯЗАТЕЛЬНО используй слово ДЕНЬГИ на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и ДЕНЬГИ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
    elif section == "shadow":
        cid = card_id if card_id else random.randint(50, 63)
        prompt = f"{base_info} Сделай Вступление (короткий панч) и разбор ТЕНЬ (анализ Лилит и Селены, теневая сторона личности). ОБЯЗАТЕЛЬНО используй слово ТЕНЬ на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ and ТЕНЬ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
    elif section == "final":
        cid = card_id if card_id else random.randint(0, 21)
        prompt = f"{base_info} Сделай Вступление (короткий панч) и ФИНАЛ (Итоговый вердикт и совет в стиле 'Живи с этим'). ОБЯЗАТЕЛЬНО используй слово ФИНАЛ на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и ФИНАЛ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
    elif section == "synastry":
        cid = card_id if card_id else random.randint(0, 21)
        prompt = f"{base_info} Сделай разбор совместимости (СИНАСТРИЯ). Имя партнера: {partner_name}, дата рождения партнера: {partner_date}. Сделай жесткий разбор мэтча. Опиши сильные стороны и кармические узлы связи. ОБЯЗАТЕЛЬНО используй слово СИНАСТРИЯ на отдельной строке перед основным разбором. Выдели заголовок СИНАСТРИЯ КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
    elif section == "antitaro":
        cid = card_id if card_id else random.randint(0, 77)
        prompt = f"{base_info} Сделай Вступление (короткий панч) и разбор АНТИТАРО (максимально циничный, деструктивный и жесткий совет наоборот, снятие розовых очков). ОБЯЗАТЕЛЬНО используй слово АНТИТАРО на отдельной строке перед основным разбором. Выдели заголовки ВСТУПЛЕНИЕ и АНТИТАРО КАПСОМ. В самом конце текста ОБЯЗАТЕЛЬНО добавь строку с ID карты Таро в формате: ID_ТАРО: {cid}. Вплети этот ID прямо в свой прогноз.{style_instruction}"
    elif section == "card_of_day":
        card_name = card_data.get('name', 'Твою карту') if card_data else "Твою карту"
        prompt = f"{base_info} Выдай карту дня: {card_name} (как ежедневный гороскоп, но в стиле Таро). ОБЯЗАТЕЛЬНО используй слово КАРТА ДНЯ на отдельной строке перед основным разбором. Выдели заголовок КАРТА ДНЯ КАПСОМ. {style_instruction}"
    else:
        return None

    if return_json:
        prompt += "\n\nТЕБЕ НУЖНО ВЕРНУТЬ СТРОГО JSON ОБЪЕКТ со следующими ключами:\n" \
                  "1. 'text': Главный текст разбора (ВСТУПЛЕНИЕ и основной блок).\n" \
                  "2. 'shadow_side': Теневая сторона карты или личности (2-3 предложения).\n" \
                  "3. 'activation_level': Уровень активации энергии (число от 0 до 100).\n" \
                  "4. 'activation_comment': Комментарий к уровню активации (1 предложение).\n" \
                  "5. 'affirmations': Личные аффирмации/мантры (3-4 штуки).\n" \
                  "6. 'next_activation_date': Дата следующей мощной активации (например, '23 октября 2024').\n" \
                  "7. 'thirty_day_forecast': Мини-прогноз на ближайшие 30 дней.\n" \
                  "8. 'activation_recommendations': Рекомендации по активации (камень, цвет, аромат, ритуал).\n" \
                  "9. 'star_code': Персональный Звёздный код/Магическая печать (уникальная фраза-код).\n" \
                  "10. 'energy_map': Описание визуальной Карты энергий (какие планеты влияют).\n\n" \
                  "Отвечай только JSON."

        res = await generate_text(prompt, json_mode=True, skin=skin)
        if res:
            try:
                clean = clean_ai_json(res)
                return json.loads(clean)
            except Exception as e:
                logger.error(f"Failed to parse JSON from AI: {e}. Raw text: {res[:300]}...")
                return {"text": res}
        return {"text": "Ошибка генерации."}
    else:
        return await generate_text(prompt, skin=skin)
