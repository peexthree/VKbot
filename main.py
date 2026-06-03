import ast
import asyncio
import datetime
import json
import os
import warnings
import sentry_sdk
from aiohttp import web
from loguru import logger

sentry_dsn = os.environ.get("SENTRY_DSN", "")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.environ.get("SENTRY_ENV", "production"),
        release=os.environ.get("SENTRY_RELEASE", "1.0.0"),
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

# Настройка логирования loguru (отключаем enqueue из-за проблем с пиклингом динамических исключений vkbottle)
logger.add("logs/bot_{time}.log", rotation="10 MB", enqueue=False)

# КРИТИЧЕСКИЙ ХАК ДЛЯ PYTHON 3.14+
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    for attr in ("Num", "Str", "Bytes", "NameConstant", "Ellipsis"):
        if not hasattr(ast, attr):
            setattr(ast, attr, type(attr, (ast.Constant,), {}))

async def handle_ping(request):
    return web.Response(text="Bot is alive")

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
            await bot.process_event(data)
        except Exception as e:
            logger.error(f"Critical error in bot.process_event ({event_type}): {e}. Data: {json.dumps(data, ensure_ascii=False)}")

    asyncio.create_task(_safe_process())
    return web.Response(text="ok")

async def main():
    from ai_service import close_session, generate_text, init_session
    from database import get_all_users, init_db, update_user
    from modules.bot_init import bot
    from vkbottle import Keyboard, KeyboardButtonColor, Callback

    # Инициализация глобальной сессии aiohttp
    init_session()
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
    bot.labeler.load(services.labeler)
    bot.labeler.load(tarot.labeler)
    bot.labeler.load(support.labeler)
    bot.labeler.load(registration.labeler)
    bot.labeler.load(profile.labeler)
    bot.labeler.load(payments.labeler)

    import modules.admin as admin
    bot.labeler.load(admin.labeler)

    # Фоновая задача для ежедневных прогнозов и реактивации
    async def daily_forecast_cron():
        while True:
            now = datetime.datetime.now(datetime.timezone.utc)
            # Перенос на 13:00 по Москве (10:00 UTC)
            if now.hour == 10 and now.minute == 30:
                users = await get_all_users()

                async def process_reactivation(user):
                    vk_id = user.get("vk_id")
                    last_active = user.get("last_active_date")
                    if not last_active: return

                    last_date = datetime.datetime.fromisoformat(last_active).date()
                    days_since = (now.date() - last_date).days

                    if days_since == 3:
                        tags = user.get("tags", [])
                        tag_context = f" Твои запросы по теме {tags[0]} все еще ждут ответа." if tags else ""
                        msg = f"✦ ТВОЯ МАТРИЦА ЗАТУХАЕТ ✦\n\nТебя не было 3 дня. Потоки энергии слабеют.{tag_context} Вернись и забери свой ежедневный дар (+100 ✨), пока связь не прервалась полностью."
                        try: await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)
                        except Exception: pass
                    elif days_since == 7:
                        msg = "✦ КРИТИЧЕСКИЙ РАЗРЫВ ✦\n\nПрошла неделя. Твой Проводник ждет тебя. Сегодня я приготовил для тебя особенный инсайт, доступный только 24 часа. Не дай своим тайнам кануть в бездну."
                        try: await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)
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
                            await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=0)
                            purchased["last_cart_stage"] = 1
                            await update_user(vk_id, {"purchased_sections": purchased})
                        except Exception: pass
                    elif elapsed_hours >= 24 and last_cart_stage == 1:
                        msg = "✦ ВОЗВРАЩЕНИЕ К ЗВЕЗДАМ ✦\n\nВчера ты остановился в шаге от ответов. За это время 42 человека уже открыли свои Карты Судьбы. Звезды еще ждут. Возвращаю тебе твою персональную скидку 15% до конца дня."
                        try:
                            kb = Keyboard(inline=True).add(Callback("ЗАБРАТЬ СО СКИДКОЙ 15% ✨", payload={"cmd": "buy", "type": "abandoned_15", "key": last_cart_item}), color=KeyboardButtonColor.POSITIVE)
                            await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=0)
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
                                    await bot.api.messages.send(peer_id=vk_id, message=msg, keyboard=kb.get_json(), random_id=0)
                                    purchased["card_of_day_notif_sent"] = now.isoformat()
                                    await update_user(vk_id, {"purchased_sections": purchased})
                                except Exception: pass

                    from cache import get_temp_birth_data
                    temp_birth = await get_temp_birth_data(vk_id)
                    if not temp_birth or not temp_birth.get("city"):
                        return
                    expires_str = user.get("transit_sub_expires_at")
                    has_sub = False
                    if expires_str:
                        try:
                            exp_date = datetime.datetime.fromisoformat(expires_str)
                            if exp_date > now:
                                has_sub = True
                        except ValueError:
                            pass
                    trial_days = user.get("transit_trial_days", 0)
                    if has_sub or trial_days < 3:
                        core_profile = user.get("core_profile", "")
                        active_skin = user.get("active_skin", "olesya")
                        tags = user.get("tags", [])
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
                            f"КРИТИЧЕСКОЕ ПРАВИЛО: Строгий запрет на выделение текста маркерами. Никаких звездочек. Никакого жирного шрифта. Используй только короткие тире (-) для создания списков и структуры."
                        )
                        forecast = await generate_text(prompt, skin=active_skin)
                        if forecast:
                            from ai_service import extract_tags
                            async def extract_and_save_tags(v_id: int, text: str):
                                new_tags = await extract_tags(text)
                                if new_tags:
                                    from database import update_user
                                    await update_user(v_id, {"tags": new_tags})
                            asyncio.create_task(extract_and_save_tags(vk_id, forecast))
                            try:
                                # Форматирование даты
                                date_str = now.strftime("%d.%m")

                                kb = Keyboard(inline=True).add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

                                await bot.api.messages.send(
                                    peer_id=vk_id,
                                    message=f"✦ ШЕПОТ ЗВЕЗД ✦\n📅 {date_str}\n-----------------\n{forecast}\n-----------------\n✨ Твой Проводник всегда рядом.",
                                    keyboard=kb.get_json(),
                                    random_id=0
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
                                    [{"action": {"type": "callback", "payload": json.dumps({"cmd": "tariff_page", "idx": 0}), "label": "Спутник 7 дней"}, "color": "secondary"}],
                                    [{"action": {"type": "callback", "payload": json.dumps({"cmd": "tariff_page", "idx": 1}), "label": "Оракул 30 дней"}, "color": "primary"}],
                                    [{"action": {"type": "callback", "payload": json.dumps({"cmd": "tariff_page", "idx": 2}), "label": "VIP Архив"}, "color": "positive"}]
                                ]
                            }
                            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
                            msg = "Твои карты на сегодня разложены. Виден сильный энергетический сдвиг, но... ТРИАЛ ОКОНЧЕН. Канал связи с Оракулом закрыт. Матрица требует энергообмена."
                            await bot.api.messages.send(
                                peer_id=vk_id,
                                message=msg,
                                keyboard=kb_json,
                                random_id=0
                            )
                            await update_user(vk_id, {"transit_trial_days": 4})
                        except Exception as e:
                            logger.error(f"Ошибка: {str(e)}")
                sem = asyncio.Semaphore(5)
                async def sem_process_user(u):
                    async with sem:
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

    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_post('/vk/callback', handle_vk_webhook)

    from modules.payments.yookassa import yookassa_webhook
    app.router.add_post('/yookassa/webhook', yookassa_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"Сервер запущен на порту {port}. Бот слушает сообщения...")

    try:
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        logger.error(f"Global unhandled error: {str(e)}")
    finally:
        try:
            from modules.utils import _typing_tasks, stop_dynamic_typing
            for peer_id in list(_typing_tasks.keys()):
                await stop_dynamic_typing(peer_id)
        except Exception as e:
            logger.error(f"Error cleaning up typing tasks: {str(e)}")
        await close_session()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
