import ast
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    for attr in ("Num", "Str", "Bytes", "NameConstant", "Ellipsis"):
        if not hasattr(ast, attr):
            setattr(ast, attr, type(attr, (ast.Constant,), {}))

import os
import asyncio
import json
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import textwrap

async def handle_ping(request):
    from aiohttp import web
    return web.Response(text="Bot is alive")

async def main():
    from aiohttp import web
    from modules.bot_init import bot
    from database import get_all_users, update_user, init_db
    from ai_service import generate_text
    from modules import utils

    


    # Init database
    await init_db()

    # Share bot with utils


    # Import and load modules
    import modules.registration as registration
    import modules.profile as profile
    import modules.services as services
    import modules.tarot as tarot
    import modules.payments as payments

    bot.labeler.load(registration.labeler)
    bot.labeler.load(profile.labeler)
    bot.labeler.load(services.labeler)
    bot.labeler.load(tarot.labeler)
    bot.labeler.load(payments.labeler)

    async def daily_forecast_cron():
        while True:
            now = datetime.datetime.now(datetime.timezone.utc)
            if now.hour == 12 and now.minute == 0:
                users = await get_all_users()

                async def process_user_transit(user):
                    vk_id = user.get("vk_id")
                    if not vk_id or not user.get("birth_city"): return

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
                        prompt = (
                            f"Сгенерируй геймифицированный прогноз на день. "
                            f"В начале добавь шкалу энергии: 'Энергия [Случайное число 1-10]/10'. "
                            f"Укажи 'Фокус:' и 'Уязвимость:'. Опирайся на этот профиль: {core_profile}. "
                            f"Коротко, жестко."
                        )
                        forecast = await generate_text(prompt, skin=active_skin)
                        if forecast:
                            try:
                                await bot.api.messages.send(
                                    peer_id=vk_id,
                                    message=f"✦ ЕЖЕДНЕВНЫЙ ТРАНЗИТ ✦\n\n{forecast}",
                                    random_id=0
                                )
                                if not has_sub:
                                    await update_user(vk_id, {"transit_trial_days": trial_days + 1})
                            except Exception as e:
                                print(f"Не удалось отправить транзит {vk_id}: {e}")
                    elif trial_days == 3:
                        try:
                            keyboard_obj = {
                                "inline": True,
                                "buttons": [
                                    [{"action": {"type": "text", "label": "ТАРИФ 1 (99 РУБ)"}, "color": "secondary"}],
                                    [{"action": {"type": "text", "label": "ТАРИФ 2 (290 РУБ)"}, "color": "primary"}],
                                    [{"action": {"type": "text", "label": "VIP БАНДЛ (590 РУБ)"}, "color": "positive"}]
                                ]
                            }
                            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
                            msg = "Твои карты на сегодня разложены. Виден сильный энергетический сдвиг, но... ТРИАЛ ОКОНЧЕН. Канал связи с Оракулом закрыт. Матрица требует энергообмена."

                            try:
                                await bot.api.messages.send(
                                    peer_id=vk_id,
                                    message=msg,
                                    keyboard=kb_json,
                                    random_id=0
                                )
                            except Exception:
                                await bot.api.messages.send(
                                    peer_id=vk_id,
                                    message=msg,
                                    random_id=0
                                )
                            await update_user(vk_id, {"transit_trial_days": 4})
                        except Exception as e:
                            print(f"Не удалось отправить upsell {vk_id}: {e}")

                sem = asyncio.Semaphore(5)
                async def sem_process_user(u):
                    async with sem:
                        await process_user_transit(u)

                await asyncio.gather(*(sem_process_user(u) for u in users))
                await asyncio.sleep(3660)
            else:
                await asyncio.sleep(60)

    bot.loop_wrapper._running = True
    asyncio.create_task(bot.run_polling())
    asyncio.create_task(daily_forecast_cron())
    
    app = web.Application()
    app.router.add_get('/', handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"Сервер запущен на порту {port}. Бот слушает сообщения...")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
