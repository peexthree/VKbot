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

async def main():
    from ai_service import close_session, generate_text, init_session
    from database import get_all_users, init_db, update_user
    from modules.bot_init import bot

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
    from modules.middlewares import ThrottleMiddleware

    bot.labeler.message_view.register_middleware(ThrottleMiddleware)

    bot.labeler.load(registration.labeler)
    bot.labeler.load(profile.labeler)
    bot.labeler.load(services.labeler)
    bot.labeler.load(tarot.labeler)
    bot.labeler.load(payments.labeler)

    import modules.admin as admin
    bot.labeler.load(admin.labeler)

    # Фоновая задача для ежедневных прогнозов и реактивации
    async def daily_forecast_cron():
        while True:
            now = datetime.datetime.now(datetime.timezone.utc)
            if now.hour == 12 and now.minute == 0:
                users = await get_all_users()

                async def process_reactivation(user):
                    vk_id = user.get("vk_id")
                    last_active = user.get("last_active_date")
                    if not last_active: return

                    last_date = datetime.datetime.fromisoformat(last_active).date()
                    days_since = (now.date() - last_date).days

                    if days_since == 3:
                        msg = "✦ ТВОЯ МАТРИЦА ЗАТУХАЕТ ✦\n\nТебя не было 3 дня. Потоки энергии слабеют. Вернись и забери свой ежедневный дар, пока связь не прервалась полностью."
                        try: await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)
                        except Exception: pass
                    elif days_since == 7:
                        msg = "✦ КРИТИЧЕСКИЙ РАЗРЫВ ✦\n\nПрошла неделя. Твой Проводник ждет тебя. Сегодня я приготовил для тебя особенный инсайт, доступный только 24 часа. Не дай своим тайнам кануть в бездну."
                        try: await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)
                        except Exception: pass

                async def process_user_transit(user):
                    vk_id = user.get("vk_id")
                    if not vk_id or not user.get("birth_city"):
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
                        prompt = (
                            f"Сгенерируй геймифицированный прогноз на день. "
                            f"В начале добавь шкалу энергии: 'Энергия [Случайное число 1-10]/10'. "
                            f"Укажи 'Фокус:' и 'Уязвимость:'. Опирайся на этот профиль: {core_profile}. "
                            f"Учитывай текущие теги пользователя (его главные боли/запросы): {tags_str}. "
                            f"Сделай к ним тонкую отсылку. Коротко, жестко. "
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
                                await bot.api.messages.send(
                                    peer_id=vk_id,
                                    message=f"✦ ЕЖЕДНЕВНЫЙ ТРАНЗИТ ✦\n-----------------\n{forecast}\n-----------------",
                                    random_id=0
                                )
                                if not has_sub:
                                    await update_user(vk_id, {"transit_trial_days": trial_days + 1})
                            except Exception as e:
                                logger.error(f"Ошибка: {str(e)}")

                    await process_reactivation(user)
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
    asyncio.create_task(bot.run_polling())
    from modules.utils import warmup_task
    asyncio.create_task(warmup_task())
    asyncio.create_task(daily_forecast_cron())

    app = web.Application()
    app.router.add_get('/', handle_ping)
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
