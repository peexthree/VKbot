import asyncio
import base64
import os
import re
from loguru import logger
import aiohttp
from configs.models import MODELS
from prompts.base import BASE_SYSTEM_INSTRUCTION
from prompts.personas import SKIN_MAP
from ai.core import get_session

SANITIZATION_TABLE = str.maketrans({
    '*': '',
    '#': '',
    '_': '',
    '—': '-',
    '`': '',
    '~': ''
})

STOP_WORDS_18PLUS = [
    "порно", "секс", "эротика", "насилие", "инцест", "педофилия", "убийство",
    "самоубийство", "суицид", "расчлененка", "наркотики", "шлюха", "проститутка",
    "членосос", "пизда", "хуй", "ебать", "трахаться", "порнуха", "извращение", "грязь"
]

_cached_api_keys = None

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

async def generate_text(prompt: str, json_mode: bool = False, skin: str = "olesya", image_urls: list[str] = None) -> str | None:
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
    session = get_session()

    for model, version in MODELS:
        for api_key in api_keys:
            url = f"https://generativelanguage.googleapis.com/{version}/{model}:generateContent?key={api_key}"

            # Премиальная инструкция для более глубоких ответов
            premium_context = (
                "Используй метафоры высокого уровня, но сочетай их с современным технологическим или психологическим контекстом. "
                "Твой ответ должен казаться невероятно личным и глубоким. Избегай общих фраз. "
                "Структурируй ответ так, чтобы он был удобен для чтения в мессенджере (короткие абзацы, тире)."
            )

            if json_mode:
                final_prompt = f"{tov_instruction}\n{BASE_SYSTEM_INSTRUCTION}\n{premium_context}\n{prompt.strip()}\nОтветь строго в формате JSON."
            else:
                final_prompt = f"{tov_instruction}\n{BASE_SYSTEM_INSTRUCTION}\n{premium_context}\n{prompt.strip()}"

            parts = [{"text": final_prompt}]
            if image_urls:
                for img_url in image_urls:
                    try:
                        async with session.get(img_url, timeout=10) as img_resp:
                            if img_resp.status == 200:
                                img_data = await img_resp.read()
                                parts.append({
                                    "inline_data": {
                                        "mime_type": "image/jpeg",
                                        "data": base64.b64encode(img_data).decode("utf-8")
                                    }
                                })
                    except Exception as e:
                        logger.error(f"Failed to fetch image for AI: {e}")

            payload = {
                "contents": [{"parts": parts}]
            }

            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60 if image_urls else 25)) as resp:
                    if resp.status == 200:
                        res_data = await resp.json()
                        try:
                            parts = res_data['candidates'][0]['content']['parts']
                            text = "".join(part["text"] for part in parts if "text" in part and not part.get("thought"))

                            if not text and parts:
                                text = parts[-1].get("text", "")

                            if not json_mode:
                                text = text.translate(SANITIZATION_TABLE)

                            # Добавляем маркер для TTS если нужно (будущая фича)
                            # text = "[VOICE_ENABLED] " + text

                            return text
                        except (KeyError, IndexError):
                            continue
                    elif resp.status == 429:
                        logger.warning(f"Rate limit hit for text generation ({model}). Retrying with backoff...")
                        for i in range(1, 4):
                            await asyncio.sleep(2 ** i)
                            try:
                                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=25)) as retry_resp:
                                    if retry_resp.status == 200:
                                        res_data = await retry_resp.json()
                                        parts = res_data['candidates'][0]['content']['parts']
                                        text = "".join(part["text"] for part in parts if "text" in part and not part.get("thought"))
                                        if not text and parts:
                                            text = parts[-1].get("text", "")
                                        if not json_mode:
                                            text = text.translate(SANITIZATION_TABLE)
                                        return text
                                    elif retry_resp.status != 429:
                                        break
                            except Exception:
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

def clean_ai_json(raw: str) -> str:
    if not raw:
        return raw
    cleaned = re.sub(r'```(?:json)?', '', raw, flags=re.IGNORECASE).strip()
    cleaned = cleaned.strip('`').strip()
    return cleaned
