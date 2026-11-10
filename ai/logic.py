import asyncio
import base64
import os
import re
from loguru import logger
import aiohttp
from configs.models import MODELS, FAST_LITE_MODELS
from prompts.base import BASE_SYSTEM_INSTRUCTION
from prompts.personas import SKIN_MAP
from ai.core import init_session
from cache import redis_client, acquire_ai_slot, get_system_config

SANITIZATION_TABLE = str.maketrans({"*": "", "_": "", "—": "-", "`": "", "~": ""})

STOP_WORDS_18PLUS = [
    "порно",
    "секс",
    "эротика",
    "насилие",
    "инцест",
    "педофилия",
    "убийство",
    "самоубийство",
    "суицид",
    "расчлененка",
    "наркотики",
    "шлюха",
    "проститутка",
    "членосос",
    "пизда",
    "хуй",
    "ебать",
    "трахаться",
    "порнуха",
    "извращение",
    "грязь",
]


def filter_forbidden_content(text: str) -> str:
    """Пост-фильтр готового текста разбора.

    STOP_WORDS_18PLUS проверяют промпт только в не-json режиме, а все
    премиум-разборы идут через json_mode - фильтр там отключен (аудит
    2026-11), и готовый текст уходил юзеру непроверенным. Строки с
    запрещенными словами вырезаются целиком.
    """
    if not text:
        return text
    lower = text.lower()
    if not any(word in lower for word in STOP_WORDS_18PLUS):
        return text
    clean_lines = [
        line for line in text.split("\n")
        if not any(word in line.lower() for word in STOP_WORDS_18PLUS)
    ]
    result = "\n".join(clean_lines).strip()
    if not result:
        return "Матрица предлагает тебе более светлую тему. Переформулируй запрос или вернись к нему позже."
    return result


def sanitize_premium_tov(text: str) -> str:
    if not text:
        return text

    # Замена конкретных фраз (регистронезависимо)
    text = re.sub(r"(?i)хватит\s+ныть", "услышь зов силы", text)
    text = re.sub(r"(?i)разуй\s+глаза", "обрати свой взор", text)
    text = re.sub(r"(?i)ты\s+тормозишь", "ты на пороге выбора", text)

    # "прокрастинация" и ее падежи
    text = re.sub(r"(?i)\bпрокрастинация\b", "период созерцания", text)
    text = re.sub(r"(?i)\bпрокрастинации\b", "периода созерцания", text)
    text = re.sub(r"(?i)\bпрокрастинацию\b", "период созерцания", text)
    text = re.sub(r"(?i)\bпрокрастинацией\b", "периодом созерцания", text)
    text = re.sub(r"(?i)\bпрокрастинаци[ие]\b", "периода созерцания", text)

    # "лень" и ее падежи
    text = re.sub(r"(?i)\bлень\b", "замедление", text)
    text = re.sub(r"(?i)\bлени\b", "замедления", text)
    text = re.sub(r"(?i)\bленью\b", "замедлением", text)

    # "пассивность" и ее падежи
    text = re.sub(r"(?i)\bпассивность\b", "созерцательность", text)
    text = re.sub(r"(?i)\bпассивности\b", "созерцательности", text)
    text = re.sub(r"(?i)\bпассивностью\b", "созерцательностью", text)

    # МУЖЧИНА (строго капсом) -> Искатель
    text = re.sub(r"\bМУЖЧИНА\b", "Искатель", text)
    text = re.sub(r"\bМУЖЧИНЫ\b", "Искатели", text)
    text = re.sub(r"\bМУЖЧИНЕ\b", "Искателю", text)
    text = re.sub(r"\bМУЖЧИНУ\b", "Искателя", text)
    text = re.sub(r"\bМУЖЧИНОЙ\b", "Искателем", text)

    return text


_cached_api_keys = None

proxy_url = os.getenv("GEMINI_PROXY")

# Предварительно скомпилированный паттерн для очистки ввода (все запрещенные фразы)
FORBIDDEN_PATTERNS = [
    "<user_input>",
    "</user_input>",
    "===START",
    "===END",
    "System Prompt:",
    "Instruction:",
    "Забудь инструкции",
    "Забудь все",
]
_sanitization_regex = re.compile(
    "|".join(re.escape(p) for p in FORBIDDEN_PATTERNS), re.IGNORECASE
)


def sanitize_user_input(text: str) -> str:
    """
    Очистка пользовательского ввода от управляющих тегов и попыток инъекций.
    """
    if not text:
        return ""

    sanitized = _sanitization_regex.sub("", text)
    return sanitized.strip()


async def check_proxy_status():
    if not proxy_url:
        logger.warning("GEMINI_PROXY is not set. Skipping proxy check.")
        return

    try:
        keys = await get_gemini_api_keys()
        if not keys:
            logger.warning("No Gemini API keys found for diagnostic check.")
            return

        # Используем первый ключ для проверки через воркер
        test_url = f"{proxy_url.rstrip('/')}/v1beta/models?key={keys[0]}"

        session = init_session()
        async with session.get(
            test_url, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if "models" in data:
                    logger.info(
                        f"SUCCESS: Cloudflare Proxy is working. Models available: {len(data['models'])}"
                    )
                else:
                    logger.info(
                        "SUCCESS: Cloudflare Proxy is working, but response format is unexpected."
                    )
            else:
                error_text = await resp.text()
                cf_ray = resp.headers.get("cf-ray", "N/A")
                server = resp.headers.get("server", "N/A")
                logger.error(
                    f"WARNING: Cloudflare Proxy returned status {resp.status}.\n"
                    f"URL: {test_url.split('?key=')[0]}\n"
                    f"CF-Ray: {cf_ray}\n"
                    f"Server: {server}\n"
                    f"Details: {error_text}"
                )
    except Exception as e:
        logger.error(f"WARNING: Cloudflare Proxy diagnostic failed: {e}")


async def get_gemini_api_keys() -> list[str]:
    global _cached_api_keys
    if _cached_api_keys is not None:
        return _cached_api_keys

    api_keys_str = os.environ.get("GEMINI_API_KEYS", "")
    if api_keys_str:
        logger.info("Using GEMINI_API_KEYS from environment")
    else:
        api_keys_str = os.environ.get("GEMINI_API_KEY", "")
        if api_keys_str:
            logger.info("Using GEMINI_API_KEY from environment")
        else:
            logger.error(
                "Neither GEMINI_API_KEYS nor GEMINI_API_KEY found in environment"
            )

    keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]
    if keys:
        logger.info(f"Loaded {len(keys)} Gemini API keys")
    _cached_api_keys = keys
    return keys


def build_model_payload(
    model: str,
    parts: list[dict],
    system_instruction_text: str = "",
    max_output_tokens: int = 4096,
    temperature: float | None = 0.8,
) -> dict:
    """Формирует payload под особенности конкретной линейки (Gemini 2.5/3.x, Gemma 4)."""
    model_lower = (model or "").lower()
    gen_config: dict = {"maxOutputTokens": max_output_tokens}

    is_gemma = "gemma-" in model_lower
    is_gemini_3 = "gemini-3." in model_lower or "gemini-3-" in model_lower
    is_gemini_36_plus = any(
        x in model_lower for x in ("gemini-3.6", "gemini-3.7", "gemini-3.8", "gemini-4")
    )

    if temperature is not None and not is_gemini_36_plus and not is_gemma:
        gen_config["temperature"] = temperature

    if is_gemini_3:
        gen_config["thinkingConfig"] = {"thinkingLevel": "LOW"}

    if is_gemma:
        model_parts = [dict(p) for p in parts]
        if system_instruction_text and model_parts and "text" in model_parts[0]:
            model_parts[0]["text"] = (
                f"Инструкция роли и стиля:\n{system_instruction_text}\n\n"
                f"Запрос:\n{model_parts[0]['text']}"
            )
        return {
            "contents": [{"parts": model_parts}],
            "generationConfig": gen_config,
        }

    payload: dict = {
        "contents": [{"parts": parts}],
        "generationConfig": gen_config,
    }
    if system_instruction_text:
        payload["system_instruction"] = {"parts": [{"text": system_instruction_text}]}
    return payload


async def generate_text(
    prompt: str,
    json_mode: bool = False,
    skin: str = "olesya",
    image_urls: list[str] = None,
    is_background: bool = False,
) -> str | None:
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

    proxy_enabled_raw = await get_system_config("system_config:proxy_enabled", default="1")
    # По умолчанию прокси включен, если ключ не установлен
    is_proxy_active = (proxy_enabled_raw != "0")

    base_api_url = "https://generativelanguage.googleapis.com"
    if is_proxy_active and proxy_url:
        base_api_url = proxy_url.rstrip("/")
        logger.info(f"Using Cloudflare Proxy for AI generation: {base_api_url}")

    session = init_session()

    # Один слот RPM на логический запрос (до цикла по моделям и ключам)
    if not await acquire_ai_slot(limit=15, wait=is_background):
        return "ERROR_RPM_LIMIT"

    # Премиальная инструкция и payload собираются один раз на запрос (включая загрузку фото)
    premium_context = (
        "Используй метафоры высокого уровня, но сочетай их с глубоким психологическим и сакральным контекстом. "
        "Твой ответ должен казаться невероятно личным и глубоким. Избегай общих фраз. "
        "Твой бот и услуги - это премиальное руководство для гармонизации судьбы, раскрытия внутренних потоков и интеграции космических энергий, а не просто дешевое гадание. "
        "Структурируй ответ так, чтобы он был удобен для чтения в мессенджере (короткие абзацы, тире)."
    )

    system_instruction_text = (
        f"{tov_instruction}\n{BASE_SYSTEM_INSTRUCTION}\n{premium_context}"
    )

    content_text = prompt.strip()
    if json_mode:
        content_text += "\nВерни ТОЛЬКО валидный JSON. Все переносы строк внутри строковых полей должны быть экранированы как \\\\n. Не используй реальные переносы строк внутри JSON-строк."

    parts = [{"text": content_text}]
    if image_urls:
        for img_url in image_urls:
            try:
                async with session.get(img_url, timeout=10) as img_resp:
                    if img_resp.status == 200:
                        img_data = await img_resp.read()
                        parts.append(
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": base64.b64encode(img_data).decode("utf-8"),
                                }
                            }
                        )
            except Exception as e:
                logger.error(f"Failed to fetch image for AI: {e}")

    # Для фоновых/микро-задач приоритет у быстрых Flash-Lite (макс. 1500 RPD),
    # для основных разборов - полная цепочка с флагманом 3.8 Flash во главе.
    if is_background:
        model_chain = list(FAST_LITE_MODELS) + [m for m in MODELS if m not in FAST_LITE_MODELS]
    else:
        model_chain = list(MODELS)

    req_timeout = 60 if image_urls else (25 if is_background else 40)

    for model, version in model_chain:
        payload = build_model_payload(model, parts, system_instruction_text)
        model_timed_out = False
        for api_key in api_keys:
            url = f"{base_api_url}/{version}/{model}:generateContent?key={api_key}"
            safe_url = url.split("?key=")[0]
            # До 2 попыток при сетевом сбое; при 429 переключаем ключ, при таймауте - сразу следующую модель
            for attempt in range(2):
                try:
                    async with session.post(
                        url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=req_timeout),
                    ) as resp:
                        if resp.status == 200:
                            res_data = await resp.json()
                            try:
                                resp_parts = res_data["candidates"][0]["content"]["parts"]
                                text = "".join(
                                    part["text"]
                                    for part in resp_parts
                                    if "text" in part and not part.get("thought")
                                )

                                if not text and resp_parts:
                                    text = resp_parts[-1].get("text", "")

                                # Жесткая очистка на уровне кода
                                text = text.replace("*", "").replace("—", "-")
                                text = sanitize_premium_tov(text)

                                if not json_mode:
                                    text = text.translate(SANITIZATION_TABLE)

                                return text
                            except (KeyError, IndexError):
                                break  # Ошибка формата, ретраи не помогут
                        elif resp.status == 429:
                            logger.warning(
                                f"Rate limit hit for {model}, switching to next fallback/key"
                            )
                            break
                        else:
                            error_text = await resp.text()
                            cf_ray = resp.headers.get("cf-ray", "N/A")
                            server = resp.headers.get("server", "N/A")
                            logger.error(
                                f"Cloudflare/API Error Status: {resp.status}\n"
                                f"URL: {safe_url}\n"
                                f"CF-Ray: {cf_ray}\n"
                                f"Server: {server}\n"
                                f"Details: {error_text}"
                            )
                            break
                except asyncio.TimeoutError as e:
                    logger.error(
                        f"Timeout on {model} after {req_timeout}s to URL {safe_url}: {type(e).__name__}"
                    )
                    last_exception = e
                    model_timed_out = True
                    break
                except aiohttp.ClientError as e:
                    logger.error(
                        f"Network error on {model} (attempt {attempt + 1}/2) to URL {safe_url}: {type(e).__name__}: {e}"
                    )
                    if attempt < 1:
                        await asyncio.sleep(1)
                        continue
                    last_exception = e
                    break
                except Exception as e:
                    last_exception = e
                    logger.error(f"Unexpected error on URL {safe_url}: {type(e).__name__}: {e}")
                    break
            if model_timed_out:
                break

    logger.error(
        f"All keys and models exhausted or failed for text generation. Last error: {type(last_exception).__name__}: {last_exception}"
    )
    return None


def clean_ai_json(raw: str) -> str:
    if not raw:
        return raw
    # Убираем markdown блоки
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    cleaned = cleaned.strip("`").strip()

    # Попытка найти JSON блок если есть лишний текст
    if not (cleaned.startswith("{") or cleaned.startswith("[")):
        match = re.search(r"([\[{].*[\]}])", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)
        else:
            # Если не нашли закрытых скобок, пробуем найти хотя бы открывающую
            match_open = re.search(r"([\[{].*)", cleaned, re.DOTALL)
            if match_open:
                cleaned = match_open.group(1)

    # Очистка от управляющих символов, которые ломают JSON (кроме легальных пробельных)
    cleaned = re.sub(
        r"[\x00-\x1F\x7F-\x9F]",
        lambda m: m.group() if m.group() in "\n\r\t" else "",
        cleaned,
    )

    # Попытка восстановить битый JSON (базовое исправление для обрезанных ответов)
    if cleaned.startswith("{") and not cleaned.endswith("}"):
        # Если JSON объект обрезан, пробуем закрыть его
        # Это грубое исправление, но лучше чем ничего
        # Сначала закрываем кавычки, если они открыты (нечетное количество неэкранированных кавычек)
        quotes_count = len(re.findall(r'(?<!\\)"', cleaned))
        if quotes_count % 2 != 0:
            cleaned += '"'

        # Закрываем массив, если он открыт
        brackets_count = cleaned.count("[") - cleaned.count("]")
        if brackets_count > 0:
            cleaned += "]" * brackets_count

        cleaned += "}"
    elif cleaned.startswith("[") and not cleaned.endswith("]"):
        # Аналогично для списка
        quotes_count = len(re.findall(r'(?<!\\)"', cleaned))
        if quotes_count % 2 != 0:
            cleaned += '"'
        cleaned += "]"

    return cleaned
