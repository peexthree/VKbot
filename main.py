import ast
import asyncio
import datetime
import json
import os
import warnings

import sentry_sdk
from aiohttp import web
from loguru import logger

# ====================== SENTRY ======================
sentry_dsn = os.environ.get("SENTRY_DSN", "")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.environ.get("ENV", "production"),
        release=os.environ.get("SENTRY_RELEASE", "1.0.0"),
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

# ====================== ЛОГИ ======================
logger.add("logs/bot_{time}.log", rotation="10 MB", enqueue=True, backtrace=True, diagnose=True)

# ====================== AST ХАК ДЛЯ RENDER (Python 3.14+) ======================
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    for attr in ("Num", "Str", "Bytes", "NameConstant", "Ellipsis"):
        if not hasattr(ast, attr):
            setattr(ast, attr, type(attr, (ast.Constant,), {}))

async def handle_ping(request):
    return web.Response(text="Bot is alive")

async def main():
    from ai_service import close_session, init_session
    from database import init_db
    from modules.bot_init import bot

    # Инициализация
    init_session()
    await init_db()

    # Загрузка модулей
    import modules.payments as payments
    import modules.profile as profile
    import modules.registration as registration
    import modules.services as services
    import modules.tarot as tarot
    import modules.admin as admin

    from modules.middlewares import ThrottleMiddleware
    bot.labeler.message_view.register_middleware(ThrottleMiddleware)

    bot.labeler.load(registration.labeler)
    bot.labeler.load(profile.labeler)
    bot.labeler.load(services.labeler)
    bot.labeler.load(tarot.labeler)
    bot.labeler.load(payments.labeler)
    bot.labeler.load(admin.labeler)

    # ====================== ФОНОВЫЕ ЗАДАЧИ ======================
    from modules.utils import warmup_task

    asyncio.create_task(bot.run_polling())
    asyncio.create_task(warmup_task())

    # Запуск ежедневного крона
    from modules.cron import daily_forecast_cron
    asyncio.create_task(daily_forecast_cron())

    # ====================== HEALTH-CHECK ======================
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"Сервер запущен на порту {port}. Бот работает.")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await close_session()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
