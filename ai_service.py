from __future__ import annotations
import asyncio
import json
import os
import random
import re
from typing import Any, Dict, List

import aiohttp
from loguru import logger

from configs.models import MODELS
from prompts.base import BASE_SYSTEM_INSTRUCTION
from prompts.personas import SKIN_MAP

_session: aiohttp.ClientSession | None = None
_cached_api_keys: List[str] | None = None

# Быстрая санитизация (убираем всё лишнее форматирование)
SANITIZATION_TABLE = str.maketrans({"*": "", "#": "", "_": "", "—": "-"})

STOP_WORDS_18PLUS = [
    "порно", "секс", "эротика", "насилие", "инцест", "педофилия", "убийство",
    "самоубийство", "суицид", "расчлененка", "наркотики", "шлюха", "проститутка",
    "членосос", "пизда", "хуй", "ебать", "трахаться", "порнуха", "извращение", "грязь"
]


async def init_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=90),
            connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
        )
    return _session


async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None
        logger.info("AI session closed")


async def get_gemini_api_keys() -> list[str]:
    global _cached_api_keys
    if _cached_api_keys is not None:
        return _cached_api_keys

    api_keys_str = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY", "")
    keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]
    _cached_api_keys = keys
    return keys


async def generate_text(prompt: str, json_mode: bool = False, skin: str = "olesya") -> str | None:
    """Основная генерация текста с ротацией ключей и моделями"""
    if not json_mode:
        prompt_lower = prompt.lower()
        if any(word in prompt_lower for word in STOP_WORDS_18PLUS):
            return "Матрица отвергает этот запрос. Энергия этого вопроса разрушительна или нарушает баланс. Сформулируй свой вопрос чище."

    api_keys = await get_gemini_api_keys()
    if not api_keys:
        logger.error("No Gemini API keys provided")
        return None

    tov_instruction = SKIN_MAP.get(skin, SKIN_MAP["olesya"])
    session = await init_session()

    final_prompt = (
        f"{prompt.strip()}\nОтветь строго в формате JSON."
        if json_mode
        else f"{tov_instruction}\n{BASE_SYSTEM_INSTRUCTION}{prompt.strip()}"
    )

    payload = {"contents": [{"parts": [{"text": final_prompt}]}]}

    for model, version in MODELS:
        for api_key in api_keys:
            url = f"https://generativelanguage.googleapis.com/{version}/{model}:generateContent?key={api_key}"
            for attempt in range(4):
                try:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                        if resp.status == 200:
                            res_data = await resp.json()
                            try:
                                parts = res_data["candidates"][0]["content"]["parts"]
                                text = "".join(
                                    part["text"] for part in parts
                                    if "text" in part and not part.get("thought")
                                ) or (parts[-1].get("text", "") if parts else "")
                                if not json_mode:
                                    text = text.translate(SANITIZATION_TABLE)
                                return text
                            except (KeyError, IndexError):
                                continue

                        elif resp.status == 429:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        else:
                            error_text = await resp.text()
                            logger.error(f"Gemini error {resp.status} on {model}: {error_text}")
                            break
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout on {model}, attempt {attempt + 1}")
                    continue
                except Exception as e:
                    logger.error(f"Gemini request error on {model}: {e}")
                    break

    logger.error("All Gemini keys and models exhausted or failed")
    return None


async def extract_tags(text: str) -> list[str]:
    prompt = (
        f"Проанализируй следующий эзотерический разбор: '{text}'. "
        f"Выдели 1-3 главных жестких тега (болей/фокусов). "
        f"Примеры: 'фокус-на-деньгах', 'кризис-отношений', 'выгорание'. "
        f"Верни строго JSON-список строк."
    )
    res = await generate_text(prompt, json_mode=True)
    if not res:
        return []
    try:
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", res).strip()
        tags = json.loads(clean)
        return tags if isinstance(tags, list) else []
    except Exception as e:
        logger.error(f"Ошибка парсинга тегов: {e}")
        return []


async def extract_birth_data(text: str) -> dict | None:
    prompt = (
        f"Пользователь написал: '{text}'. "
        f"Вытащи дату рождения (DD.MM.YYYY), время (HH:MM) и город. "
        f"Если времени нет — 12:00. Верни строго JSON: {{\"date\": \"15.04.1990\", \"time\": \"14:30\", \"city\": \"Москва\"}}."
    )
    res = await generate_text(prompt, json_mode=True)
    if not res:
        return None
    try:
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", res).strip()
        return json.loads(clean)
    except Exception as e:
        logger.error(f"Ошибка парсинга birth data: {e}")
        return None


# ====================== КОНФИГУРАЦИЯ СЕКЦИЙ (DRY) ======================
SECTION_CONFIG: Dict[str, Dict[str, Any]] = {
    "base": {"title": "БАЗА", "card_range": None},
    "sex": {"title": "СЕКС", "card_range": (22, 50)},
    "money": {"title": "ДЕНЬГИ", "card_range": (64, 77)},
    "shadow": {"title": "ТЕНЬ", "card_range": (50, 63)},
    "final": {"title": "ФИНАЛ", "card_range": (0, 21)},
    "synastry": {"title": "СИНАСТРИЯ", "card_range": (0, 21)},
    "antitaro": {"title": "АНТИТАРО", "card_range": (0, 77)},
    "card_of_day": {"title": "КАРТА ДНЯ", "card_range": (0, 77)},
}


def _get_card_id(section: str, card_id: str | None = None) -> str:
    if card_id is not None:
        return str(card_id)
    config = SECTION_CONFIG.get(section)
    if not config or not config["card_range"]:
        return str(random.randint(0, 77))
    min_id, max_id = config["card_range"]
    return str(random.randint(min_id, max_id))


async def generate_section(
    section: str,
    date: str,
    time: str,
    city: str,
    core_profile: str = "",
    first_name: str = "",
    sex: int = 0,
    partner_name: str = "",
    partner_date: str = "",
    skin: str = "olesya",
    card_id: str | None = None,
    card_data: dict | None = None,
    tags: list | None = None,
) -> str | None:
    """Универсальный генератор любого разбора"""
    gender_str = "МУЖЧИНА" if sex == 2 else "ЖЕНЩИНА" if sex == 1 else "НЕИЗВЕСТНО"

    base_info = f"Данные: {date}, время {time}, город {city}. ПОЛЬЗОВАТЕЛЬ — {gender_str}."
    if first_name:
        base_info += f" ИМЯ — {first_name}."
    base_info += " ОБРАЩАЙСЯ СТРОГО В ПРАВИЛЬНОМ РОДЕ. ОБЯЗАТЕЛЬНО используй слово ВСТУПЛЕНИЕ на отдельной строке."

    if core_profile:
        base_info += f" Прошлый анализ: {core_profile}."

    # Теги из Redis (память пользователя)
    if tags:
        try:
            from cache import redis_client
            mem_val = await redis_client.get("system_config:tag_memory_active")
            if mem_val is None or int(mem_val) != 0:
                base_info += f" ВАЖНО: Прошлые боли — [{', '.join(tags)}]. Начни с тонкой отсылки."
        except Exception:
            pass

    if card_data:
        base_info += (
            f" ВАЖНО: Пользователь вытянул карту '{card_data.get('name')}'. "
            f"Её значение: '{card_data.get('description')}'. "
            f"Весь разбор строится вокруг этой карты."
        )

    config = SECTION_CONFIG.get(section)
    if not config:
        logger.error(f"Неизвестная секция: {section}")
        return None

    title = config["title"]
    cid = _get_card_id(section, card_id)

    extra = ""
    if section == "synastry":
        extra = f" Имя партнёра: {partner_name}. Дата партнёра: {partner_date}."

    prompt = (
        f"{base_info}{extra} "
        f"Сделай Вступление (короткий панч) и разбор {title}. "
        f"ОБЯЗАТЕЛЬНО используй слово {title} на отдельной строке. "
        f"Выдели заголовки ВСТУПЛЕНИЕ и {title} КАПСОМ. "
        f"В самом конце ОБЯЗАТЕЛЬНО добавь строку ID_ТАРО: {cid}. "
        f"Вплети ID прямо в прогноз. "
        f"Никаких маркеров, только короткие тире (-) и КАПС. "
        f"Текст — абзацами по 2-3 предложения."
    )

    return await generate_text(prompt, skin=skin)
