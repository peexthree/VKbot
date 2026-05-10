from __future__ import annotations
import asyncio
import datetime
import os
import psutil

print(f"Memory at start: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MiB")

import sentry_sdk
from aiohttp import web
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor

os.environ["WEASYPRINT_NO_FONTS"] = "1"

from cache import acquire_lock, release_lock

sentry_dsn = os.environ.get("SENTRY_DSN", "")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.environ.get("SENTRY_ENV", "production"),
        release=os.environ.get("SENTRY_RELEASE", "1.0.0"),
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

# Настройка логирования
logger.add("logs/bot_{time}.log", rotation="10 MB", enqueue=True, backtrace=True, diagnose=True)


async def handle_ping(request):
    return web.Response(text="Bot is alive")


async def daily_forecast_cron():
    """Фоновая задача ежедневных транзитов (SaaS-ready)"""
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)

        if now.hour == 12 and now.minute == 0:
            lock_acquired = await acquire_lock("daily_forecast_cron", ttl=3600)
            if not lock_acquired:
                logger.info("daily_forecast_cron уже запущен в другом экземпляре")
                await asyncio.sleep(60)
                continue

            try:
                logger.info("Запуск ежедневного транзита для всех пользователей")
                from database import get_all_users, update_user
                from ai_service import generate_text, extract_tags

                users = await get_all_users()

                sem = asyncio.Semaphore(8)  # ограничиваем нагрузку

                async def process_user(user):
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
                    if not (has_sub or trial_days < 3):
                        if trial_days == 3:
                            # Триал закончился — отправляем предложение тарифа
                            kb = Keyboard(inline=True)
                            kb.add(KeyboardButtonColor.SECONDARY, label="Спутник 7 дней",
                                   payload={"cmd": "tariff_page", "idx": 0})
                            kb.row()
                            kb.add(KeyboardButtonColor.PRIMARY, label="Оракул 30 дней",
                                   payload={"cmd": "tariff_page", "idx": 1})
                            kb.row()
                            kb.add(KeyboardButtonColor.POSITIVE, label="VIP Архив",
                                   payload={"cmd": "tariff_page", "idx": 2})

                            msg = ("Твои карты на сегодня разложены. Виден сильный энергетический сдвиг, "
                                   "но... ТРИАЛ ОКОНЧЕН. Канал связи с Оракулом закрыт. Матрица требует энергообмена.")

                            try:
                                from modules.bot_init import bot
                                await bot.api.messages.send(
                                    peer_id=vk_id,
                                    message=msg,
                                    keyboard=kb.get_json(),
                                    random_id=0
                                )
                                await update_user(vk_id, {"transit_trial_days": 4})
                            except Exception as e:
                                logger.error(f"Ошибка отправки trial-end пользователю {vk_id}: {e}")
                        return

                    # Есть подписка или триал активен → отправляем прогноз
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
                        try:
                            from modules.bot_init import bot
                            await bot.api.messages.send(
                                peer_id=vk_id,
                                message=f"✦ ЕЖЕДНЕВНЫЙ ТРАНЗИТ ✦\n-----------------\n{forecast}\n-----------------",
                                random_id=0
                            )
                            if not has_sub:
                                await update_user(vk_id, {"transit_trial_days": trial_days + 1})

                            # Сохраняем новые теги (в фоне)
                            new_tags = await extract_tags(forecast)
                            if new_tags:
                                await update_user(vk_id, {"tags": new_tags})
                        except Exception as e:
                            logger.error(f"Ошибка отправки транзита пользователю {vk_id}: {e}")

                async def sem_process(u):
                    async with sem:
                        await process_user(u)

                await asyncio.gather(*(sem_process(u) for u in users), return_exceptions=True)
                logger.info(f"Ежедневный транзит завершён для {len(users)} пользователей")

            finally:
                await release_lock("daily_forecast_cron")

            await asyncio.sleep(3660)  # чуть больше часа
        else:
            await asyncio.sleep(60)


async def main():
    # 1. САМОЕ ПЕРВОЕ — запускаем health-check (Render должен увидеть порт)
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"[MEMORY AFTER HEALTH-CHECK] {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MiB")

    # 2. Только теперь импортируем всё остальное
    from modules.bot_init import bot
    from database import init_db
    from ai_service import init_session, close_session
    from modules.middlewares import ThrottleMiddleware

    await init_db()
    init_session()

    bot.labeler.message_view.register_middleware(ThrottleMiddleware)

    import modules.registration as registration
    import modules.profile as profile
    import modules.services as services
    import modules.tarot as tarot
    import modules.payments as payments
    import modules.admin as admin

    bot.labeler.load(registration.labeler)
    bot.labeler.load(profile.labeler)
    bot.labeler.load(services.labeler)
    bot.labeler.load(tarot.labeler)
    bot.labeler.load(payments.labeler)
    bot.labeler.load(admin.labeler)

    # Запускаем бота
    asyncio.create_task(bot.run_polling())

    # Временно закомментируем самые тяжёлые задачи для теста
    # asyncio.create_task(warmup_task())
    # asyncio.create_task(daily_forecast_cron())

    logger.info(f"Сервер запущен на порту {port}. Бот слушает сообщения...")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        # Очистка
        from modules.utils import _typing_tasks, stop_dynamic_typing
        for peer_id in list(_typing_tasks.keys()):
            await stop_dynamic_typing(peer_id)
        await close_session()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.critical(f"Критическая ошибка запуска: {e}")
