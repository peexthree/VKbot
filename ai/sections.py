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
    'трансформация-личности', 'защита-и-очищение', 'мудрость-предков', 'баланс-стихий', 'зов-сердца',
    'свобода'
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
    res = await generate_text(prompt, json_mode=True, is_background=True)
    if not res:
        return []
    try:
        clean = clean_ai_json(res)

        # Ленивая регулярка: остановится на первой же закрывающей скобке ]
        match = re.search(r'\[.*?\]', clean, re.DOTALL)
        if match:
            clean = match.group(0)

        data = json.loads(clean, strict=False)
        tags = []
        if isinstance(data, list):
            tags = data
        elif isinstance(data, dict):
            # Если ИИ вернул объект вместо списка, ищем список внутри
            for val in data.values():
                if isinstance(val, list):
                    tags = val
                    break

        # Фильтрация: оставляем только теги из белого списка
        filtered_tags = [t for t in tags if t in AVAILABLE_TAGS]
        return filtered_tags
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
    res = await generate_text(prompt, json_mode=True, is_background=True)
    if not res or res == "ERROR_RPM_LIMIT":
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
    base_info = f"Данные пользователя: дата рождения {date}, время {time}, город рождения <user_input>{s_city}</user_input>. {gender_instruction}"
    if current_date:
        base_info += f" СЕГОДНЯШНЯЯ ДАТА: {current_date}."
    if first_name:
        s_first_name = sanitize_user_input(first_name)
        base_info += f" ИМЯ ПОЛЬЗОВАТЕЛЯ - <user_input>{s_first_name}</user_input>."

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
        if isinstance(tags, str):
            try:
                import ast
                tags = ast.literal_eval(tags)
            except Exception:
                tags = [tags]

        if isinstance(tags, list):
            clean_tags = [str(t) for t in tags if len(str(t)) > 2 and str(t) not in ["[", "]", "{", "}"]]
            if clean_tags:
                tags_str = ", ".join(clean_tags)
                base_info += f" ВАЖНО: Я помню наши прошлые темы: [{tags_str}]. " \
                             f"Используй это, чтобы наш диалог был глубоким и личным."

    if card_id and not card_data:
        card_data = get_card_data(card_id)

    if card_data:
        base_info += f" ВАЖНО: Пользователь вытянул карту Таро: '{card_data.get('name')}'. Ее базовое значение: '{card_data.get('description')}'. Построй весь свой разбор вокруг энергии и символизма этой карты."

    style_instruction = (
        " ВАЖНО: Соблюдай свой уникальный стиль персонажа! Никаких маркеров форматирования, "
        "только короткие тире (-) и КАПС для акцентов и заголовков. "
        "СТРОЖАЙШИЙ ЗАПРЕТ на любые звездочки и длинные тире. "
        "Текст должен разбиваться на абзацы по 2-3 предложения."
    )

    from prompts.services import get_group_prompt, SERVICE_GROUP_MAP
    group = SERVICE_GROUP_MAP.get(section, "E")

    # Формируем context_info для шаблона промпта
    context_info = base_info

    if section == "sigil":
        wish_text = partner_date or "Удача и Изобилие"
        raw_prompt_template = get_group_prompt(section)
        prompt = raw_prompt_template.format(wish_text=wish_text)
    else:
        if section == "oculomancy":
            context_info += f" Ритуал Окуломантии. Пользователь предоставил фотографию своего глаза для мистического анализа радужной оболочки."
        elif section == "palmistry":
            context_info += f" Ритуал Хиромантии. Пользователь прислал фотографии своих ладоней (левой и правой) для детального разбора линий судьбы, сердца, ума и жизни."
        elif section == "dream":
            dream_text = partner_date or "Неизвестный сон"
            context_info += f" Толкование снов. Пользователю приснился следующий сон: <user_input>{dream_text}</user_input>. Проведи разбор символов подсознания."
        elif section == "egyptian_oracle":
            from modules.tarot.secret_arts_logic import get_random_egyptian_oracle
            drawn = get_random_egyptian_oracle()
            drawn_str = "; ".join([f"{d['name']} ({d['desc']})" for d in drawn])
            context_info += f" Древнеегипетский Оракул вытащил 3 свитка богов: {drawn_str}."
        elif section == "shadow_oracle":
            from modules.tarot.secret_arts_logic import get_random_shadow_oracle
            drawn = get_random_shadow_oracle()
            drawn_str = "; ".join([f"{d['name']} ({d['desc']})" for d in drawn])
            context_info += f" Теневой Оракул Лилит выявил 3 руны теней по Юнгу: {drawn_str}."
        elif section == "totem":
            context_info += f" Тотемный шаманский квиз. Выборы пользователя в квизе: {partner_date}."
        elif section == "karma":
            context_info += f" Кармический навигатор. Выборы пользователя в кармическом квизе: {partner_date}."
        elif section == "astro_geo":
            location = partner_date or "Место силы"
            context_info += f" Астро-Картография. Анализ географической точки силы пользователя в локации: '<user_input>{location}</user_input>'."
        elif section == "alchemist":
            from modules.tarot.secret_arts_logic import calculate_alchemy_element
            el = calculate_alchemy_element(date)
            context_info += f" Цифровой Алхимик. Расчет определил ведущий первоэлемент пользователя: {el['name']} ({el['latin']}) {el['symbol']}. Базовое свойство: {el['desc']}."
        elif section == "chrono":
            context_info += f" Хроно-Прогноз. Персональные мистические биоритмы и ведьминские часы успеха на месяц вперед."
        elif section == "charoslov":
            context_info += f" Славянский Чарослов. Древнеславянские обереги, слова силы и утренние ведовские практики защиты/привлечения блага."
        elif section == "sex":
            context_info += f" Разбор СТРАСТЬ (анализ Венеры и Марса, отношение к любви и близости)."
        elif section == "money":
            context_info += f" Разбор ИЗОБИЛИЕ (анализ 2-го и 10-го домов, самореализация и процветание)."
        elif section == "shadow":
            context_info += f" Разбор ТЕНЬ (анализ Лилит и Селены, скрытые уголки души)."
        elif section == "final":
            context_info += f" Разбор ПУТЬ (Итоговое напутствие в жизни и светлый совет для души)."
        elif section == "synastry":
            s_partner_name = sanitize_user_input(partner_name)
            s_partner_date = sanitize_user_input(partner_date)
            context_info += f" Разбор СОЮЗ (совместимость партнеров). Имя партнера: <user_input>{s_partner_name}</user_input>, данные рождения партнера: <user_input>{s_partner_date}</user_input>."
        elif section == "antitaro":
            context_info += f" Разбор ОТКРОВЕНИЕ (честный, глубокий взгляд на то, что мешает счастью, освобождение от иллюзий)."
        elif section == "destiny_card":
            context_info += f" Разбор КАРТА СУДЬБЫ (главный жизненный путь, предназначение, кармические задачи)."
        elif section == "card_of_day":
            card_name = card_data.get('name', 'Твою карту') if card_data else "Твою карту"
            context_info += f" Карта дня: {card_name}."

        raw_prompt_template = get_group_prompt(section)
        prompt = raw_prompt_template.format(context_info=context_info)

    # Приклеиваем style_instruction в самый конец
    prompt += f"\n{style_instruction}"

    effective_json_mode = return_json

    if effective_json_mode:
        res = await generate_text(prompt, json_mode=True, skin=skin, image_urls=image_urls, is_background=False)
        if res == "ERROR_RPM_LIMIT":
            return {"text": "ERROR_RPM_LIMIT"}
        if res:
            try:
                clean = clean_ai_json(res)
                if not (clean.strip().startswith('{') or clean.strip().startswith('[')):
                    return res.replace('\\\\n', '\n').replace('\\n', '\n')
                data = json.loads(clean, strict=False)
                for k, v in data.items():
                    if isinstance(v, str):
                        data[k] = v.replace('\\\\n', '\n').replace('\\n', '\n')
                    elif isinstance(v, list):
                        data[k] = [i.replace('\\\\n', '\n').replace('\\n', '\n') if isinstance(i, str) else i for i in v]
                return data
            except Exception as e:
                logger.error(f"Failed to parse JSON from AI: {e}. Attempting manual extraction.")
                return res.replace('\\\\n', '\n').replace('\\n', '\n')
        return {"text": "Ошибка генерации."}
    else:
        res = await generate_text(prompt, skin=skin, image_urls=image_urls, is_background=False)
        if res:
            return res.replace('\\\\n', '\n').replace('\\n', '\n')
        return res
