import ast
import asyncio
import datetime
import json
import os
import random
import re
import warnings
import hashlib
import hmac
import base64
from urllib.parse import parse_qsl
import sentry_sdk
from modules.utils.logic import get_safe_tags
from modules.utils.seasonal import seasonal_prompt_line
import aiohttp
from aiohttp import web
from loguru import logger

sentry_dsn = os.environ.get("SENTRY_DSN", "")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.environ.get("SENTRY_ENV", "production"),
        release=os.environ.get("SENTRY_RELEASE", "1.0.0"),
        # 100% трейсинг/профилирование - лишние деньги и ПДн в Sentry (аудит 2026-11)
        traces_sample_rate=0.2,
        profiles_sample_rate=0.2,
    )

# Настройка логирования loguru (отключаем enqueue из-за проблем с пиклингом динамических исключений vkbottle).
# stdout только INFO: DEBUG-дампы всех API-запросов vkbottle в консоль Render
# тормозили обработку и раздували логи; полные DEBUG остаются в файле.
import sys as _sys

logger.remove()
logger.add(_sys.stdout, level="INFO")
logger.add("logs/bot_{time}.log", rotation="10 MB", enqueue=False, level="DEBUG")

import logging
logging.getLogger("vkbottle").setLevel(logging.INFO)

# КРИТИЧЕСКИЙ ХАК ДЛЯ PYTHON 3.14+
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    for attr in ("Num", "Str", "Bytes", "NameConstant", "Ellipsis"):
        if not hasattr(ast, attr):
            setattr(ast, attr, type(attr, (ast.Constant,), {}))

_START_TIME = datetime.datetime.now(datetime.timezone.utc).isoformat()

async def handle_ping(request):
    return web.Response(text="Bot is alive")

async def handle_diag(request):
    import time
    from modules.bot_init import bot

    diag = {
        "status": "ok",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "start_time": _START_TIME,
        "tests": {}
    }

    # 1. VK API
    t0 = time.time()
    try:
        vk_res = await bot.api.request("utils.getServerTime", {})
        diag["tests"]["vk_api"] = {
            "status": "ok",
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "server_time": vk_res.get("response")
        }
    except Exception as e:
        diag["tests"]["vk_api"] = {
            "status": "error",
            "error": str(e),
            "latency_ms": round((time.time() - t0) * 1000, 1)
        }

    # 2. Supabase DB
    t0 = time.time()
    try:
        from database.core import session
        from database.config import URL, HEADERS, TABLE_NAME
        if session and URL:
            async with session.get(f"{URL}/rest/v1/{TABLE_NAME}?select=vk_id&limit=1", headers=HEADERS) as r:
                diag["tests"]["supabase"] = {
                    "status": "ok" if r.status in (200, 206) else f"http_{r.status}",
                    "latency_ms": round((time.time() - t0) * 1000, 1),
                    "http_status": r.status
                }
        else:
            diag["tests"]["supabase"] = {"status": "not_initialized"}
    except Exception as e:
        diag["tests"]["supabase"] = {
            "status": "error",
            "error": str(e),
            "latency_ms": round((time.time() - t0) * 1000, 1)
        }

    # 3. Upstash Redis
    t0 = time.time()
    try:
        from cache import redis_client
        res = await redis_client.get("diag:ping")
        diag["tests"]["redis"] = {
            "status": "ok",
            "latency_ms": round((time.time() - t0) * 1000, 1)
        }
    except Exception as e:
        diag["tests"]["redis"] = {
            "status": "error",
            "error": str(e),
            "latency_ms": round((time.time() - t0) * 1000, 1)
        }

    # 4. Gemini API & Cloudflare Proxy
    t0 = time.time()
    try:
        from ai.logic import get_gemini_api_keys, proxy_url
        keys = await get_gemini_api_keys()
        if not keys:
            diag["tests"]["gemini_proxy"] = {"status": "no_keys"}
        else:
            base_url = proxy_url.rstrip("/") if proxy_url else "https://generativelanguage.googleapis.com"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as t_sess:
                async with t_sess.get(f"{base_url}/v1beta/models?key={keys[0]}") as r:
                    diag["tests"]["gemini_proxy"] = {
                        "status": "ok" if r.status == 200 else f"http_{r.status}",
                        "latency_ms": round((time.time() - t0) * 1000, 1),
                        "used_proxy": bool(proxy_url),
                        "http_status": r.status
                    }
    except Exception as e:
        diag["tests"]["gemini_proxy"] = {
            "status": "error",
            "error": str(e),
            "latency_ms": round((time.time() - t0) * 1000, 1)
        }

    # 5. In-Memory State
    try:
        from cache import _memory_locks, _throttle_map, _seen_events
        diag["memory_state"] = {
            "locks": len(_memory_locks),
            "throttles": len(_throttle_map),
            "seen_events": len(_seen_events)
        }
    except Exception as e:
        diag["memory_state"] = {"error": str(e)}

    return web.json_response(diag)


async def handle_diag_proxy(request):
    """Глубокая проверка конфигурации Cloudflare Proxy и моделей Gemini (GET + POST generateContent)."""
    import time
    from urllib.parse import urlparse
    from ai.logic import get_gemini_api_keys, proxy_url
    from cache import get_system_config
    from configs.models import MODELS

    res = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "config": {},
        "models_check": {},
        "post_tests": [],
    }

    parsed = urlparse(proxy_url) if proxy_url else None
    proxy_enabled_raw = await get_system_config("system_config:proxy_enabled", default="1")
    is_proxy_active = (proxy_enabled_raw != "0")
    keys = await get_gemini_api_keys()

    res["config"] = {
        "gemini_proxy_env_set": bool(proxy_url),
        "proxy_scheme": parsed.scheme if parsed else None,
        "proxy_host": parsed.netloc if parsed else None,
        "proxy_path": parsed.path if parsed else None,
        "system_config_proxy_enabled_raw": proxy_enabled_raw,
        "is_proxy_active_in_code": is_proxy_active,
        "api_keys_count": len(keys),
        "configured_models": [f"{v}/{m}" for m, v in MODELS],
    }

    if not keys:
        res["error"] = "No Gemini API keys found"
        return web.json_response(res)

    api_key = keys[0]
    proxy_base = proxy_url.rstrip("/") if proxy_url else None
    direct_base = "https://generativelanguage.googleapis.com"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
        # 1. Получаем реальный список моделей через прокси (или напрямую)
        list_base = proxy_base or direct_base
        available_gen_models = []
        try:
            t0 = time.time()
            async with sess.get(f"{list_base}/v1beta/models?key={api_key}") as r:
                lat = round((time.time() - t0) * 1000, 1)
                if r.status == 200:
                    data = await r.json()
                    for m in data.get("models", []):
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods:
                            available_gen_models.append(m.get("name"))
                    res["models_check"] = {
                        "status": "ok",
                        "latency_ms": lat,
                        "total_generateContent_models": len(available_gen_models),
                        "flash_models_available": [m for m in available_gen_models if "flash" in (m or "").lower()],
                        "configured_models_present": {
                            m: (m in available_gen_models) for m, _ in MODELS
                        },
                    }
                else:
                    body = (await r.text())[:300]
                    res["models_check"] = {"status": f"http_{r.status}", "latency_ms": lat, "body": body}
        except Exception as e:
            res["models_check"] = {"status": "error", "error": str(e)}

        # 2. Реальный POST generateContent (с system_instruction, как в боте)
        test_payload = {
            "contents": [{"parts": [{"text": "Reply with one word: OK"}]}],
            "system_instruction": {"parts": [{"text": "Be concise."}]},
            "generationConfig": {"maxOutputTokens": 128, "temperature": 0.1},
        }

        async def _probe_post(label: str, base_url: str, model: str, version: str):
            url = f"{base_url}/{version}/{model}:generateContent?key={api_key}"
            t0 = time.time()
            try:
                async with sess.post(url, json=test_payload) as r:
                    lat = round((time.time() - t0) * 1000, 1)
                    headers_info = {
                        "server": r.headers.get("server"),
                        "cf-ray": r.headers.get("cf-ray"),
                        "content-type": r.headers.get("content-type"),
                    }
                    if r.status == 200:
                        data = await r.json()
                        txt = ""
                        try:
                            parts = data["candidates"][0]["content"]["parts"]
                            txt = "".join(
                                p.get("text", "") for p in parts if "text" in p and not p.get("thought")
                            ).strip()
                            if not txt and parts:
                                txt = parts[-1].get("text", "")
                        except Exception:
                            txt = str(data)[:150]
                        return {
                            "target": label,
                            "model": f"{version}/{model}",
                            "status": "ok",
                            "http_status": 200,
                            "latency_ms": lat,
                            "reply": txt[:100],
                            "headers": headers_info,
                        }
                    else:
                        err_body = (await r.text())[:300]
                        return {
                            "target": label,
                            "model": f"{version}/{model}",
                            "status": f"http_{r.status}",
                            "http_status": r.status,
                            "latency_ms": lat,
                            "error_body": err_body,
                            "headers": headers_info,
                        }
            except Exception as e:
                return {
                    "target": label,
                    "model": f"{version}/{model}",
                    "status": "error",
                    "latency_ms": round((time.time() - t0) * 1000, 1),
                    "error": f"{type(e).__name__}: {e}",
                }

        check_all = request.query.get("all") == "1"
        models_to_probe = MODELS if check_all else [MODELS[0], MODELS[1]]
        if proxy_base:
            for model, version in models_to_probe:
                res["post_tests"].append(await _probe_post("proxy", proxy_base, model, version))

        first_model, first_ver = MODELS[0]
        res["post_tests"].append(await _probe_post("direct", direct_base, first_model, first_ver))

    return web.json_response(res)

def verify_vk_signature(query_string: str, secret: str) -> bool:
    """Проверка подписи параметров запуска VK Mini App"""
    try:
        # Очищаем секрет от возможных пробелов по краям
        secret = secret.strip()

        # 1. Разбираем строку, оставляем только параметры с префиксом vk_
        query_params = dict(parse_qsl(query_string, keep_blank_values=True))
        if "sign" not in query_params:
            return False

        vk_sign = query_params.pop("sign")

        # 2. Сортируем ключи и создаем строку в формате key=value
        # Фильтруем параметры: только те, что начинаются на vk_,
        # исключая vk_share_ и vk_group_ (они не участвуют в подписи)
        sorted_keys = sorted([
            k for k in query_params.keys()
            if k.startswith("vk_") and not k.startswith("vk_share_") and not k.startswith("vk_group_")
        ])
        check_str = "&".join([f"{k}={query_params[k]}" for k in sorted_keys])

        # 3. HMAC-SHA256
        hash_code = hmac.new(
            secret.encode("utf-8"),
            check_str.encode("utf-8"),
            hashlib.sha256
        ).digest()

        # 4. Base64 с заменой символов (стандарт для VK)
        expected_sign = base64.b64encode(hash_code).decode("utf-8")
        expected_sign = expected_sign.replace("+", "-").replace("/", "_").rstrip("=")

        # Принудительно очищаем обе строки от пробелов и символов переноса строки
        clean_expected = str(expected_sign).strip()
        clean_vk_sign = str(vk_sign).strip()

        if not hmac.compare_digest(clean_expected, clean_vk_sign):
            logger.warning(f"Signature mismatch! Expected (computed): {clean_expected} | Received from VK: {clean_vk_sign}")
            return False

        return True
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False

async def handle_user_info(request):
    """Эндпоинт для получения данных пользователя в Мини-приложении"""
    # Явная обработка preflight OPTIONS запросов
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': 'https://vkbotmini.vercel.app',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'X-VK-Params, Content-Type',
        }
        return web.Response(headers=headers)

    from database import get_user
    from modules.utils.logic import calculate_user_rank, calculate_exp_progress

    vk_params = request.headers.get("X-VK-Params")
    logger.debug(f"Params received in X-VK-Params: {vk_params}")

    if not vk_params:
        return web.json_response({"error": "Missing X-VK-Params header"}, status=400)

    app_secret = os.environ.get("VK_MINI_APP_SECRET")
    if not app_secret:
        logger.error("VK_MINI_APP_SECRET is not set in environment")
        return web.json_response({"error": "Server configuration error"}, status=500)

    if not verify_vk_signature(vk_params, app_secret):
        return web.json_response({"error": "Invalid signature"}, status=403)

    try:
        params_dict = dict(parse_qsl(vk_params))
        vk_user_id = int(params_dict.get("vk_user_id", 0))
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid vk_user_id"}, status=400)

    if not vk_user_id:
        return web.json_response({"error": "vk_user_id not found in params"}, status=400)

    user = await get_user(vk_user_id)
    if not user:
        return web.json_response({"error": "User not found"}, status=404)

    level, rank = calculate_user_rank(user)

    # Расчет cycle_days
    created_at_str = user.get("created_at")
    cycle_days = 0
    if created_at_str:
        try:
            created_at = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            now = datetime.datetime.now(datetime.timezone.utc)
            cycle_days = (now - created_at).days
        except Exception as e:
            logger.error(f"Error calculating cycle_days: {e}")

    # Расчет grimoire_count (уникальные карты 0-78)
    unlocked_cards = user.get("unlocked_cards") or {}
    grimoire_count = len(unlocked_cards)

    # syndicate_count
    purchased = user.get("purchased_sections") or {}
    syndicate_count = purchased.get("syndicate_count", 0)

    # exp_progress
    exp_progress = calculate_exp_progress(user)

    return web.json_response({
        "balance": int(user.get("balance", 0) or 0),
        "level": level,
        "status": rank,
        "cycle_days": max(0, cycle_days),
        "active_skin": user.get("active_skin", "olesya"),
        "grimoire_count": grimoire_count,
        "syndicate_count": syndicate_count,
        "visit_streak": user.get("visit_streak", 0),
        "exp_progress": exp_progress
    })

async def handle_grimoire(request):
    """Эндпоинт для получения истории раскладов пользователя (Гримуар)"""
    from database import get_user

    vk_params = request.headers.get("X-VK-Params")
    if not vk_params:
        return web.json_response({"error": "Missing X-VK-Params header"}, status=400)

    app_secret = os.environ.get("VK_MINI_APP_SECRET")
    if not app_secret:
        logger.error("VK_MINI_APP_SECRET is not set in environment")
        return web.json_response({"error": "Server configuration error"}, status=500)

    if not verify_vk_signature(vk_params, app_secret):
        return web.json_response({"error": "Invalid signature"}, status=403)

    try:
        params_dict = dict(parse_qsl(vk_params))
        vk_user_id = int(params_dict.get("vk_user_id", 0))
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid vk_user_id"}, status=400)

    if not vk_user_id:
        return web.json_response({"error": "vk_user_id not found in params"}, status=400)

    user = await get_user(vk_user_id)
    if not user:
        return web.json_response({"error": "User not found"}, status=404)

    history = user.get("readings_history") or []
    if not isinstance(history, list):
        history = []

    # Обработка истории: расчет ID, экстракция названия карты, сортировка
    formatted_history = []
    for item in history:
        text = item.get("text", "")
        # Попытка достать название карты из текста: "🃏 Шут — Новые начала"
        card_match = re.search(r"🃏 (.*?) —", text)
        title = card_match.group(1) if card_match else item.get("title", "Разбор")

        # Генерация уникального ID на основе контента
        content_str = f"{item.get('title')}{item.get('date')}{text}"
        item_id = hashlib.sha256(content_str.encode()).hexdigest()[:16]

        formatted_history.append({
            "id": item_id,
            "title": title,
            "date": item.get("date", ""),
            "text": text
        })

    # Сортировка от новых к старым (реверс, так как добавляются в конец)
    formatted_history = formatted_history[::-1]

    return web.json_response(formatted_history)

def sanitize_photo_sizes(data: dict) -> dict:
    """Исправляет неизвестные типы размеров фото, чтобы vkbottle не падал"""
    if not isinstance(data, dict):
        return data

    try:
        if data.get("type") == "message_new":
            # В зависимости от версии API VK, объект сообщения может быть в 'object' или 'object'['message']
            obj = data.get("object", {})
            message = obj.get("message") if "message" in obj else obj

            if isinstance(message, dict):
                for attachment in message.get("attachments", []):
                    if attachment.get("type") == "photo":
                        photo = attachment.get("photo", {})
                        for size in photo.get("sizes", []):
                            t = size.get("type")
                            if t and t not in {'s','m','x','o','p','q','r','k','l','y','z','c','w','a','b','e','i','d','j','temp','h','g','n','f','max'}:
                                logger.warning(f"Unknown photo size type '{t}' → replaced with 'z'")
                                size["type"] = "z"   # самый большой доступный тип
        return data
    except Exception as e:
        logger.warning(f"Sanitizer error: {e}")
        return data

async def handle_vk_webhook(request):
    from modules.bot_init import bot
    from vkbottle import GroupEventType

    # VK Confirmation Code
    confirmation_code = os.environ.get("VK_CONFIRMATION_CODE")
    secret_key = os.environ.get("VK_SECRET_KEY")

    try:
        data = await request.json()
        data = sanitize_photo_sizes(data)
    except Exception:
        return web.Response(text="Invalid JSON", status=400)

    event_type = data.get("type")

    # 1. Проверка подтверждения ДО проверки секретного ключа (ВК может не слать секрет в confirmation)
    if event_type == "confirmation":
        return web.Response(text=confirmation_code)

    # 2. Проверка секретного ключа для всех остальных событий
    incoming_secret = data.get("secret")
    if secret_key and incoming_secret != secret_key:
        logger.warning(f"Invalid secret key from {request.remote}. Incoming: {incoming_secret}")
        return web.Response(text="Forbidden", status=403)

    # 3. Защита от падения vkbottle на неизвестных типах событий
    try:
        # Проверяем, существует ли тип события в перечислении vkbottle
        # Это предотвращает ValueError внутри vkbottle при разборе события
        if not any(e.value == event_type for e in GroupEventType):
            logger.debug(f"Skipping unsupported event type: {event_type}")
            return web.Response(text="ok")
    except Exception:
        # Если GroupEventType не инициализирован или возникла иная ошибка
        return web.Response(text="ok")

    # Process event safely in a task to prevent crashing the main loop
    async def _safe_process():
        try:
            # Дедупликация (аудит 2026-11): VK повторяет доставку при таймауте
            # ответа - без проверки event_id возможна двойная генерация платного
            # контента
            event_id = str(data.get("event_id") or (data.get("object") or {}).get("event_id") or "")
            if event_id:
                try:
                    from cache import check_and_mark_event_seen

                    # Мгновенный in-memory дедуп: исключает повторную обработку ретраев VK
                    # без сетевых запросов к Upstash (0мс задержки)
                    if not check_and_mark_event_seen(f"vk_event:{event_id}", ttl=60.0):
                        logger.debug(f"Duplicate event {event_type} skipped ({event_id})")
                        return
                except Exception as dedup_err:
                    logger.warning(f"Webhook dedup error (proceeding fail-open): {dedup_err}")
            await bot.process_event(data)
        except Exception as e:
            logger.error(f"Critical error in bot.process_event ({event_type}): {e}. Data: {json.dumps(data, ensure_ascii=False)}")

    asyncio.create_task(_safe_process())
    return web.Response(text="ok")

async def main():
    from ai_service import close_session, generate_text, init_session, check_proxy_status
    from database import get_all_users, init_db, update_user
    from modules.bot_init import bot
    from vkbottle import Keyboard, KeyboardButtonColor, Callback

    # Инициализация глобальной сессии aiohttp
    init_session()

    # Проверка прокси при старте
    await check_proxy_status()

    # Инициализация базы данных
    await init_db()

    # Импорт и регистрация обработчиков модулей
    import modules.payments as payments
    import modules.profile as profile
    import modules.registration as registration
    import modules.services as services
    import modules.tarot as tarot
    import modules.support as support
    from modules.middlewares import ThrottleMiddleware

    bot.labeler.message_view.register_middleware(ThrottleMiddleware)

    # ПОРЯДОК ЗАГРУЗКИ ВАЖЕН: сначала загружаем обработчики со стейтами (услуги, таро, саппорт),
    # чтобы они имели приоритет над общими командами вроде "сброс" или "профиль"
    # Импорт обработчиков "Тайных искусств"
    from modules.tarot.secret_arts_handlers import labeler as secret_arts_labeler

    bot.labeler.load(secret_arts_labeler)
    bot.labeler.load(services.labeler)
    bot.labeler.load(tarot.labeler)
    bot.labeler.load(support.labeler)
    bot.labeler.load(registration.labeler)
    bot.labeler.load(profile.labeler)
    bot.labeler.load(payments.labeler)

    from modules.autoposter import labeler as autoposter_labeler
    bot.labeler.load(autoposter_labeler)

    import modules.admin as admin
    bot.labeler.load(admin.labeler)

    # FSM-зеркало: восстанавливаем state_dispenser из Redis, чтобы стейты
    # (email-ввод, вопросы Оракулу и т.д.) переживали рестарт Render (аудит 2026-11)
    from database.states import restore_fsm_dispenser

    await restore_fsm_dispenser(bot)

    # Фоновая задача для ежедневных прогнозов и реактивации
    async def daily_forecast_cron():
        while True:
            now = datetime.datetime.now(datetime.timezone.utc)
            # Перенос на 13:00 по Москве (10:00 UTC)
            if now.hour == 10 and now.minute == 30:
                # Защита окна: деплой/долгая итерация больше не пропускает
                # рассылку молча - ключ в Redis гарантирует один запуск в день
                from cache import redis_client as _cron_redis

                _cron_key = f"cron:daily_forecast:{now.date().isoformat()}"
                if not await _cron_redis.set(_cron_key, "1", nx=True, ex=172800):
                    await asyncio.sleep(30)
                    continue
                users = await get_all_users()

                async def process_reactivation(user):
                    vk_id = user.get("vk_id")
                    last_active = user.get("last_active_date")
                    if not last_active: return

                    last_date = datetime.datetime.fromisoformat(last_active).date()
                    days_since = (now.date() - last_date).days

                    if days_since == 3:
                        tags = get_safe_tags(user)
                        tag_context = ""
                        if tags:
                            lucky_tag = random.choice(tags)
                            tag_context = f" Твои запросы по теме «{lucky_tag}» все еще ждут ответа."
                        msg = f"✦ ТВОЯ МАТРИЦА ЗАТУХАЕТ ✦\n\nТебя не было 3 дня. Потоки энергии слабеют.{tag_context} Вернись и забери свой ежедневный дар (+100 ✨), пока связь не прервалась полностью."
                        try:
                            kb = Keyboard(inline=True).add(Callback("✨ ЗАБРАТЬ ДАР", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.POSITIVE)
                            kb.row().add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
                            await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                        except Exception: pass
                    elif days_since == 7:
                        msg = "✦ КРИТИЧЕСКИЙ РАЗРЫВ ✦\n\nПрошла неделя. Твой Проводник ждет тебя. Сегодня я приготовил для тебя особенный инсайт, доступный только 24 часа. Не дай своим тайнам кануть в бездну."
                        try:
                            kb = Keyboard(inline=True).add(Callback("🔮 ПОЛУЧИТЬ ИНСАЙТ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.POSITIVE)
                            kb.row().add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
                            await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                        except Exception: pass

                async def process_abandoned_cart(user):
                    vk_id = user.get("vk_id")
                    purchased = user.get("purchased_sections", {})
                    last_cart_item = purchased.get("last_cart_item")
                    last_cart_at = purchased.get("last_cart_at")
                    last_cart_stage = purchased.get("last_cart_stage", 0)
                    if not last_cart_at or not last_cart_item: return

                    cart_time = datetime.datetime.fromisoformat(last_cart_at)
                    now = datetime.datetime.now(datetime.timezone.utc)
                    elapsed_hours = (now - cart_time).total_seconds() / 3600.0

                    if 1 <= elapsed_hours < 24 and last_cart_stage == 0:
                        msg = "✦ ТВОЙ ВЫБОР ВСЕ ЕЩЕ ЖДЕТ ✦\n\nЯ заметил, что ты интересовался энергией звезд, но связь оборвалась. Только для тебя — Матрица дает скидку 10% на пополнение в течение следующего часа. Используй этот шанс."
                        try:
                            kb = Keyboard(inline=True).add(Callback("ЗАБРАТЬ СО СКИДКОЙ ✨", payload={"cmd": "buy", "type": "abandoned_10", "key": last_cart_item}), color=KeyboardButtonColor.POSITIVE)
                            await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                            purchased["last_cart_stage"] = 1
                            await update_user(vk_id, {"purchased_sections": purchased})
                        except Exception: pass
                    elif elapsed_hours >= 24 and last_cart_stage == 1:
                        msg = "✦ ВОЗВРАЩЕНИЕ К ЗВЕЗДАМ ✦\n\nВчера ты остановился в шаге от ответов. За это время 42 человека уже открыли свои Карты Судьбы. Звезды еще ждут. Возвращаю тебе твою персональную скидку 15% до конца дня."
                        try:
                            kb = Keyboard(inline=True).add(Callback("ЗАБРАТЬ СО СКИДКОЙ 15% ✨", payload={"cmd": "buy", "type": "abandoned_15", "key": last_cart_item}), color=KeyboardButtonColor.POSITIVE)
                            await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                            # Очищаем, чтобы не спамить больше
                            purchased["last_cart_at"] = None
                            purchased["last_cart_stage"] = 2
                            await update_user(vk_id, {"purchased_sections": purchased})
                        except Exception: pass

                async def process_user_transit(user):
                    vk_id = user.get("vk_id")
                    if not vk_id: return

                    # Проверка доступности Карты Дня
                    purchased = user.get("purchased_sections", {})
                    last_used_str = purchased.get("card_of_day_last_used")
                    if last_used_str:
                        last_time = datetime.datetime.fromisoformat(last_used_str.replace('Z', '+00:00'))
                        if (now - last_time).total_seconds() >= 24 * 3600:
                            # Проверяем, не отправляли ли мы уже уведомление сегодня
                            last_notif = purchased.get("card_of_day_notif_sent")
                            if not last_notif or datetime.datetime.fromisoformat(last_notif).date() < now.date():
                                msg = "🌟 ТВОЯ КАРТА ДНЯ ЖДЕТ ТЕБЯ 🌟\n\nЭнергия восстановилась. Приди и узнай, что приготовили тебе звезды сегодня."
                                try:
                                    kb = Keyboard(inline=True).add(Callback("🃏 ПОЛУЧИТЬ КАРТУ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.POSITIVE)
                                    kb.row().add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
                                    await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                                    purchased["card_of_day_notif_sent"] = now.isoformat()
                                    await update_user(vk_id, {"purchased_sections": purchased})
                                except Exception: pass

                    from cache import get_temp_birth_data
                    temp_birth = await get_temp_birth_data(vk_id)

                    expires_str = user.get("transit_sub_expires_at")
                    has_sub = False
                    if expires_str:
                        try:
                            exp_date = datetime.datetime.fromisoformat(expires_str)
                            if exp_date > now:
                                has_sub = True

                                # Уведомление об истечении подписки
                                days_left = (exp_date.date() - now.date()).days
                                if days_left in [1, 3]:
                                    notif_key = f"sub_expiry_{days_left}_at"
                                    if purchased.get(notif_key) != expires_str:
                                        day_word = "день" if days_left == 1 else "дня"
                                        msg = f"🔮 ТВОЙ ПРЕМИУМ-ПЕРИОД ИСТЕКАЕТ 🔮\n\nДо конца действия транзита осталось {days_left} {day_word}. Связь с Оракулом может прерваться в самый неподходящий момент. Продли доступ заранее, чтобы не терять поток энергии."
                                        try:
                                            kb = Keyboard(inline=True).add(Callback("💎 ПРОДЛИТЬ ДОСТУП", payload={"cmd": "tariff_page", "idx": 2}), color=KeyboardButtonColor.POSITIVE)
                                            kb.row().add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
                                            await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                                            purchased[notif_key] = expires_str
                                            await update_user(vk_id, {"purchased_sections": purchased})
                                        except Exception: pass
                        except (ValueError, TypeError):
                            pass
                    trial_days = user.get("transit_trial_days", 0)
                    is_muted = purchased.get("whisper_muted", False)

                    # FOMO TRIGGER (День 2: Эмоциональный пуш)
                    if (has_sub or trial_days < 3) and not is_muted and not (temp_birth and temp_birth.get("city")):
                        if not purchased.get("whisper_fomo_sent"):
                            msg = (
                                "🔮 Матрица перестроилась, и твои планеты вошли в критический сектор. "
                                "В целях безопасности твои данные были очищены, "
                                "и я больше не слышу шепот звезд для тебя.\n\n"
                                "Нажми на кнопку ниже, подтверди время рождения и узнай, какой вызов приготовила тебе Вселенная на сегодня."
                            )
                            try:
                                kb = Keyboard(inline=True).add(Callback("🔮 УЗНАТЬ ПРОГНОЗ", payload={"cmd": "whisper_fomo_reverify"}), color=KeyboardButtonColor.POSITIVE)
                                await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                                purchased["whisper_fomo_sent"] = True
                                await update_user(vk_id, {"purchased_sections": purchased})
                            except Exception: pass

                    if (has_sub or trial_days < 3) and not is_muted and temp_birth and temp_birth.get("city"):
                        from cache import get_core_profile
                        core_profile = await get_core_profile(vk_id)
                        active_skin = user.get("active_skin", "olesya")
                        tags = get_safe_tags(user)
                        tags_str = ", ".join(tags) if tags else "отсутствует"

                        purchased = user.get("purchased_sections", {})
                        sex_val = purchased.get("sex_val", 0)

                        if sex_val == 1:
                            gender_instruction = "ПОЛЬЗОВАТЕЛЬ - ЖЕНЩИНА. ОБРАЩАЙСЯ К НЕЙ В ЖЕНСКОМ РОДЕ."
                        elif sex_val == 2:
                            gender_instruction = "ПОЛЬЗОВАТЕЛЬ - МУЖЧИНА. ОБРАЩАЙСЯ К НЕМУ В МУЖСКОМ РОДЕ."
                        else:
                            gender_instruction = "ОБРАЩАЙСЯ К ПОЛЬЗОВАТЕЛЮ НЕЙТРАЛЬНО, БЕЗ УКАЗАНИЯ ПОЛА."

                        # Добавляем данные рождения в промпт для точности
                        b_info = f"Дата: {temp_birth.get('date')}, Время: {temp_birth.get('time')}, Город: {temp_birth.get('city')}."
                        prompt = (
                            f"Сгенерируй геймифицированный прогноз на день. "
                            f"{gender_instruction} Данные пользователя: {b_info}. "
                            f"Используй метафоры звезд, энергетических потоков и внутреннего света. "
                            f"В начале добавь шкалу энергии: '🌕 Энергия: [Случайное число 1-10]/10'. "
                            f"Укажи '✨ Фокус дня:' и '🌙 Уязвимость:'. "
                            f"Опирайся на этот профиль: {core_profile}. "
                            f"Учитывай текущие теги пользователя (его главные боли/запросы): {tags_str}. "
                            f"Сделай к ним тонкую, поддерживающую отсылку. "
                            + seasonal_prompt_line()
                            + f" "
                            f"КРИТИЧЕСКОЕ ПРАВИЛО: Строгий запрет на выделение текста маркерами. Никаких звездочек. Никакого жирного шрифта. Используй только короткие тире (-) для создания списков и структуры."
                        )
                        forecast = await generate_text(prompt, skin=active_skin, is_background=True)
                        if forecast and forecast != "ERROR_RPM_LIMIT":
                            from ai_service import extract_tags
                            async def extract_and_save_tags(v_id: int, text: str):
                                new_tags = await extract_tags(text)
                                if new_tags:
                                    # Теги накапливаются (последние 10), а не перезаписываются
                                    from database import get_user, update_user

                                    _u = await get_user(v_id)
                                    old_tags = (_u or {}).get("tags") or []
                                    if not isinstance(old_tags, list):
                                        old_tags = []
                                    merged_tags = list(dict.fromkeys(old_tags + new_tags))[-10:]
                                    await update_user(v_id, {"tags": merged_tags})
                            asyncio.create_task(extract_and_save_tags(vk_id, forecast))
                            try:
                                # Форматирование даты
                                date_str = now.strftime("%d.%m")

                                kb = Keyboard(inline=True).add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

                                await bot.api.messages.send(
                                    peer_id=vk_id,
                                    message=f"✦ ШЕПОТ ЗВЕЗД ✦\n📅 {date_str}\n-----------------\n{forecast}\n-----------------\n✨ Твой Проводник всегда рядом.",
                                    keyboard=kb.get_json(),
                                    random_id=random.getrandbits(63)
                                )
                                if not has_sub:
                                    await update_user(vk_id, {"transit_trial_days": trial_days + 1})
                            except Exception as e:
                                logger.error(f"Ошибка: {str(e)}")

                    await process_reactivation(user)
                    await process_abandoned_cart(user)
                    if trial_days == 3:
                        try:
                            keyboard_obj = {
                                "inline": True,
                                "buttons": [
                                    [{"action": {"type": "callback", "payload": json.dumps({"cmd": "tariff_page", "idx": 0}), "label": "⚡ Старт 99Р"}, "color": "secondary"}],
                                    [{"action": {"type": "callback", "payload": json.dumps({"cmd": "tariff_page", "idx": 1}), "label": "🔮 Натальная Карта"}, "color": "primary"}],
                                    [{"action": {"type": "callback", "payload": json.dumps({"cmd": "tariff_page", "idx": 2}), "label": "👑 VIP 30 дней"}, "color": "positive"}]
                                ]
                            }
                            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
                            msg = "Твои карты на сегодня разложены. Виден сильный энергетический сдвиг, но... ТРИАЛ ОКОНЧЕН. Канал связи с Оракулом закрыт. Матрица требует энергообмена."
                            await bot.api.messages.send(
                                peer_id=vk_id,
                                message=msg,
                                keyboard=kb_json,
                                random_id=random.getrandbits(63)
                            )
                            await update_user(vk_id, {"transit_trial_days": 4})
                        except Exception as e:
                            logger.error(f"Ошибка: {str(e)}")
                sem = asyncio.Semaphore(5)
                async def sem_process_user(u):
                    async with sem:
                        # ПРОВЕРКА НА ИНАКТИВНОСТЬ (БОЛЕЕ 7 ДНЕЙ)
                        last_active = u.get("last_active_date")
                        purchased = u.get("purchased_sections", {})

                        if last_active:
                            try:
                                # Обрабатываем как ISO строку (может быть с Z или без)
                                last_active_clean = last_active.replace('Z', '+00:00')
                                last_date = datetime.datetime.fromisoformat(last_active_clean)
                                # Приводим now к тому же типу (offset-aware)
                                days_since = (now - last_date).days
                                if days_since > 7:
                                    # logger.debug(f"Skipping user {u.get('vk_id')} due to {days_since} days of inactivity")
                                    return
                            except Exception as e:
                                logger.error(f"Error checking inactivity for user {u.get('vk_id')}: {e}")

                        await process_user_transit(u)
                await asyncio.gather(*(sem_process_user(u) for u in users))
                # Ждем пока минута закончится, чтобы не запустить повторно в ту же минуту
                await asyncio.sleep(61)
            else:
                await asyncio.sleep(30)

    # Запуск
    bot.loop_wrapper._running = True

    use_webhooks = os.environ.get("USE_WEBHOOKS", "true").lower() == "true"

    if not use_webhooks:
        async def run_bot_with_restart():
            while True:
                try:
                    await bot.run_polling()
                except (ConnectionResetError, asyncio.TimeoutError) as e:
                    logger.warning(f"Polling connection lost: {e}. Restarting in 5s...")
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.exception(f"Critical error in polling loop: {e}. Restarting in 10s...")
                    await asyncio.sleep(10)

        asyncio.create_task(run_bot_with_restart())
    else:
        logger.info("Бот запущен в режиме WEBHOOKS")
    from modules.utils import warmup_task
    asyncio.create_task(warmup_task())

    from modules.autoposter import setup_autoposter
    setup_autoposter()

    async def daily_forecast_cron_safe():
        while True:
            try:
                await daily_forecast_cron()
            except Exception as e:
                logger.exception(f"Error in daily_forecast_cron: {e}. Restarting task in 60s...")
                await asyncio.sleep(60)

    asyncio.create_task(daily_forecast_cron_safe())

    async def render_keepalive_task():
        """Фоновый пинг для предотвращения засыпания контейнера на Render Free tier (каждые 9 минут)."""
        await asyncio.sleep(60)  # Даем серверу подняться
        app_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("APP_URL") or "https://vkbot-ad64.onrender.com"
        ping_url = f"{app_url.rstrip('/')}/"
        logger.info(f"Render keepalive task активен: периодический пинг {ping_url} (каждые 9 минут)")
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    await asyncio.sleep(540)  # 9 минут
                    async with session.get(ping_url, timeout=15) as resp:
                        logger.debug(f"Render keepalive ping: {resp.status}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"Render keepalive ping notice: {e}")

    asyncio.create_task(render_keepalive_task())

    app = web.Application()

    import aiohttp_cors
    cors = aiohttp_cors.setup(app, defaults={
        "https://vkbotmini.vercel.app": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=("GET", "POST", "OPTIONS")
        )
    })

    app.router.add_get('/', handle_ping)
    app.router.add_get('/diag', handle_diag)
    app.router.add_get('/diag/proxy', handle_diag_proxy)
    app.router.add_post('/vk/callback', handle_vk_webhook)

    user_info_resource = app.router.add_resource("/api/user/info")
    user_info_resource.add_route("GET", handle_user_info)
    cors.add(user_info_resource)

    grimoire_resource = app.router.add_resource("/api/profile/grimoire")
    grimoire_resource.add_route("GET", handle_grimoire)
    cors.add(grimoire_resource)

    from modules.payments.yookassa import yookassa_webhook
    app.router.add_post('/yookassa/webhook', yookassa_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"Сервер запущен на порту {port}. Бот слушает сообщения...")

    # Graceful shutdown (аудит 2026-11): Render шлет SIGTERM - без обработчика
    # Python завершался немедленно, finally не выполнялся, фоновые задачи не
    # отменялись, runner.cleanup() не вызывался
    stop_event = asyncio.Event()
    try:
        import signal as _signal

        _loop = asyncio.get_running_loop()
        for _sig in (_signal.SIGTERM, _signal.SIGINT):
            _loop.add_signal_handler(_sig, stop_event.set)
    except (NotImplementedError, ImportError, RuntimeError):
        pass  # Windows: NotImplementedError, остановка через KeyboardInterrupt

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    logger.info("Получен сигнал остановки - плавное завершение...")

    try:
        from modules.utils.consts import _typing_tasks
        from modules.utils.ui import stop_dynamic_typing
        for peer_id in list(_typing_tasks.keys()):
            await stop_dynamic_typing(peer_id)
    except Exception as e:
        logger.error(f"Error cleaning up typing tasks: {str(e)}")
    try:
        await close_session()
    except Exception as e:
        logger.warning(f"Error closing ai_session: {e}")
    try:
        from database.core import close_db
        await close_db()
    except Exception as e:
        logger.debug(f"Error closing db session: {e}")
    try:
        if hasattr(bot.api, "http_client") and hasattr(bot.api.http_client, "close"):
            await bot.api.http_client.close()
    except Exception as e:
        logger.debug(f"Error closing bot http client: {e}")
    try:
        await runner.cleanup()
    except Exception as e:
        logger.warning(f"runner.cleanup error: {e}")
    logger.info("Остановка завершена")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
