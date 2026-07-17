import asyncio
import base64
import os
import re
from loguru import logger
import aiohttp
from configs.models import MODELS
from prompts.base import BASE_SYSTEM_INSTRUCTION
from prompts.personas import SKIN_MAP
from ai.core import init_session
from cache import redis_client, acquire_ai_slot

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
                    f"URL: {test_url}\n"
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

    proxy_enabled_raw = await redis_client.get("system_config:proxy_enabled")
    # По умолчанию прокси включен, если ключ не установлен
    is_proxy_active = (
        bool(int(proxy_enabled_raw)) if proxy_enabled_raw is not None else True
    )

    base_api_url = "https://generativelanguage.googleapis.com"
    if is_proxy_active and proxy_url:
        base_api_url = proxy_url.rstrip("/")
        logger.info(f"Using Cloudflare Proxy for AI generation: {base_api_url}")

    session = init_session()
    for model, version in MODELS:
        for api_key in api_keys:
            url = f"{base_api_url}/{version}/{model}:generateContent?key={api_key}"

            # Премиальная инструкция для более глубоких ответов
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
                                            "data": base64.b64encode(img_data).decode(
                                                "utf-8"
                                            ),
                                        }
                                    }
                                )
                    except Exception as e:
                        logger.error(f"Failed to fetch image for AI: {e}")

            payload = {
                "contents": [{"parts": parts}],
                "system_instruction": {"parts": [{"text": system_instruction_text}]},
                "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.8},
            }

            # Ретраи для сетевых ошибок и тайм-аутов (2 попытки + основной запрос)
            for attempt in range(3):
                # Перед КАЖДОЙ попыткой (включая ретраи) запрашиваем слот в глобальном лимитере
                if not await acquire_ai_slot(limit=15, wait=is_background):
                    return "ERROR_RPM_LIMIT"

                try:
                    async with session.post(
                        url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60 if image_urls else 25),
                    ) as resp:
                        if resp.status == 200:
                            res_data = await resp.json()
                            try:
                                parts = res_data["candidates"][0]["content"]["parts"]
                                text = "".join(
                                    part["text"]
                                    for part in parts
                                    if "text" in part and not part.get("thought")
                                )

                                if not text and parts:
                                    text = parts[-1].get("text", "")

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
                                f"Rate limit hit for {model}. attempt {attempt + 1}/3"
                            )
                            if attempt < 2:
                                await asyncio.sleep(1)
                                continue
                            break
                        else:
                            error_text = await resp.text()
                            cf_ray = resp.headers.get("cf-ray", "N/A")
                            server = resp.headers.get("server", "N/A")
                            logger.error(
                                f"Cloudflare/API Error Status: {resp.status}\n"
                                f"URL: {url}\n"
                                f"CF-Ray: {cf_ray}\n"
                                f"Server: {server}\n"
                                f"Details: {error_text}"
                            )
                            break
                except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                    logger.error(
                        f"Network error/timeout on {model} (attempt {attempt + 1}/3) to URL {url}: {e}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    last_exception = e
                    break
                except Exception as e:
                    last_exception = e
                    logger.error(f"Unexpected error on URL {url}: {str(e)}")
                    break

    logger.error(
        f"All keys and models exhausted or failed for text generation. Last error: {last_exception}"
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
