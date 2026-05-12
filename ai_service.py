import asyncio
import json
import os
import random
import re

import aiohttp
from loguru import logger

_session: aiohttp.ClientSession | None = None

from configs.models import MODELS
from cards_data import get_card_data
from prompts.base import BASE_SYSTEM_INSTRUCTION
from prompts.personas import SKIN_MAP

# Translation table for faster sanitization
SANITIZATION_TABLE = str.maketrans({
    '*': '',
    '#': '',
    '_': '',
    '—': '-'
})

_cached_api_keys = None

def init_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=90),
            connector=aiohttp.TCPConnector(limit=100)
        )
    return _session

async def close_session():
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None

async def get_gemini_api_keys() -> list[str]:
    global _cached_api_keys
    if _cached_api_keys is not None:
        return _cached_api_keys

    api_keys_str = os.environ.get('GEMINI_API_KEYS', '')
    if not api_keys_str:
        api_keys_str = os.environ.get('GEMINI_API_KEY', '')
    keys = [k.strip() for k in api_keys_str.split(',') if k.strip()]
    _cached_api_keys = keys
    return keys

STOP_WORDS_18PLUS = [
    "порно", "секс", "эротика", "насилие", "инцест", "педофилия", "убийство",
    "самоубийство", "суицид", "расчлененка", "наркотики", "шлюха", "проститутка",
    "членосос", "пизда", "хуй", "ебать", "трахаться", "порнуха", "извращение", "грязь"
]

async def generate_text(prompt: str, json_mode: bool = False, skin: str = "olesya") -> str | None:
    # Pre-filtering to save tokens and prevent 18+ content execution
    if not json_mode:
        prompt_lower = prompt.lower()
        if any(word in prompt_lower for word in STOP_WORDS_18PLUS):
            return "Матрица отвергает этот запрос. Энергия этого вопроса разрушительна или нарушает баланс. Сформулируй свой вопрос чище."

    api_keys = await get_gemini_api_keys()
    if not api_keys:
        logger.error("No API keys provided")
        return None

    last_exception = Exception("Unknown error")
    tov_instruction = SKIN_MAP.get(skin, SKIN_MAP["olesya"])
    session = init_session()

    for model, version in MODELS:
        for api_key in api_keys:
            url = f"https://generativelanguage.googleapis.com/{version}/{model}:generateContent?key={api_key}"

            if json_mode:
                final_prompt = f"{prompt.strip()}\nОтветь строго в формате JSON."
            else:
                final_prompt = f"{tov_instruction}\n{BASE_SYSTEM_INSTRUCTION}{prompt.strip()}"

            payload = {
                "contents": [{"parts": [{"text": final_prompt}]}]
            }

            try:
                # Provide a per-request explicit timeout shorter than the session default (e.g. 25s)
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                    if resp.status == 200:
                        res_data = await resp.json()
                        try:
                            parts = res_data['candidates'][0]['content']['parts']
                            # Efficient string assembly using join and list comprehension
                            text = "".join(part["text"] for part in parts if "text" in part and not part.get("thought"))

                            if not text and parts:
                                text = parts[-1].get("text", "")

                            if not json_mode:
                                # Faster sanitization using translate
                                text = text.translate(SANITIZATION_TABLE)
                            return text
                        except (KeyError, IndexError):
                            continue
                    elif resp.status == 429:
                        logger.warning(f"Rate limit hit for text generation ({model}). Retrying with backoff...")
                        for i in range(1, 4):
                            await asyncio.sleep(2 ** i)
                            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=25)) as retry_resp:
                                if retry_resp.status == 200:
                                    res_data = await retry_resp.json()
                                    try:
                                        parts = res_data['candidates'][0]['content']['parts']
                                        text = "".join(part["text"] for part in parts if "text" in part and not part.get("thought"))
                                        if not text and parts:
                                            text = parts[-1].get("text", "")
                                        if not json_mode:
                                            text = text.translate(SANITIZATION_TABLE)
                                        return text
                                    except (KeyError, IndexError):
                                        pass
                                elif retry_resp.status != 429:
                                    break
                        continue
                    else:
                        error_text = await resp.text()
                        logger.error(f"Text API Error status {resp.status} on {model}. Error details: {error_text}")
                        continue
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on {model}. Trying next.")
                continue
            except Exception as e:
                last_exception = e
                logger.error(f"Ошибка: {str(e)}")
                continue

    logger.error(f"All keys and models exhausted or failed for text generation. Last error: {last_exception}")
    return None

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
        clean_res = re.sub(r"```(?:json)?\s*|\s*```", "", res).strip()
        tags = json.loads(clean_res)
        if isinstance(tags, list):
            return tags
        return []
    except Exception as e:
        logger.error(f"Ошибка парсинга тегов: {str(e)}")
        return []

async def extract_birth_data(text: str) -> dict | None:
    prompt = (
        f"Пользователь написал: '{text}'. "
        f"Вытащи дату рождения (DD.MM.YYYY), время (HH:MM) и город. "
        f"Если пользователь не указал время, по умолчанию ставь 12:00. Время всегда приводи к формату HH:MM. "
        f"Верни строго JSON: {{\"date\": \"15.04.1990\", \"time\": \"14:30\", \"city\": \"Москва\"}}."
    )
    res = await generate_text(prompt, json_mode=True)
    if not res: return None
    try:
        clean_res = re.sub(r"```(?:json)?\s*|\s*```", "", res).strip()
        return json.loads(clean_res)
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
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
    except Exception as e:
        pass

    if tags and tag_memory_active:
        tags_str = ", ".join(tags)
        base_info += f" ВАЖНО: Вижу, что прошлый раз был фокус на следующих темах/болях: [{tags_str}]. Давай посмотрим, как новая энергия решит эти проблемы. Начни текст с тонкой отсылки к этим темам, чтобы показать, что ты помнишь пользователя."

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
                import json
                return json.loads(res)
            except Exception as e:
                import logging
                logging.error(f"Failed to parse JSON from AI: {e}. Raw text: {res}")
                return {"text": res}
        return {"text": "Ошибка генерации."}
    else:
        return await generate_text(prompt, skin=skin)
