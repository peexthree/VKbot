import ast
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    for attr in ("Num", "Str", "Bytes", "NameConstant", "Ellipsis"):
        if not hasattr(ast, attr):
            setattr(ast, attr, type(attr, (ast.Constant,), {}))

import os
import asyncio

async def handle_ping(request):
    from aiohttp import web
    return web.Response(text="Bot is alive")

async def main():
    import aiohttp
    from aiohttp import web
    from vkbottle import Bot, Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
    from vkbottle.bot import Message
    from database import get_user, create_user, update_user, init_db
    from ai_service import generate_text, generate_image

    vk_token = os.environ.get("VK_TOKEN", "")
    bot = Bot(token=vk_token)
    
    await init_db()

    user_states = {}
    core_purchased_users = set()

    def get_dynamic_keyboard(user: dict | None) -> str:
        keyboard = Keyboard(inline=False)
        if not user:
            return keyboard.get_json()

        vk_id = user.get("vk_id")

        # Core sale is always available
        keyboard.add(Text("Купить полный разбор"), color=KeyboardButtonColor.PRIMARY)

        # Subscription and upsell are unlocked after core purchase
        if vk_id in core_purchased_users:
            keyboard.row()
            if not user.get("is_subscribed"):
                keyboard.add(Text("Подписка на транзиты"), color=KeyboardButtonColor.SECONDARY)
            keyboard.add(Text("Проверка совместимости"), color=KeyboardButtonColor.SECONDARY)

        return keyboard.get_json()

    @bot.on.message(text=["Начать", "start", "/start"])
    async def start_handler(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if user and user.get("free_teaser_used"):
            await message.answer("Добро пожаловать обратно в элитный астрологический сервис.", keyboard=get_dynamic_keyboard(user))
        else:
            user_states[vk_id] = {"step": "waiting_date"}
            await message.answer("Добро пожаловать. Введите дату вашего рождения (например, 15.04.1990):")

    @bot.on.message(func=lambda msg: user_states.get(msg.from_id, {}).get("step") == "waiting_date")
    async def process_date(message: Message):
        vk_id = message.from_id
        user_states[vk_id]["date"] = message.text
        user_states[vk_id]["step"] = "waiting_time"
        await message.answer("Введите время вашего рождения (например, 14:30):")

    @bot.on.message(func=lambda msg: user_states.get(msg.from_id, {}).get("step") == "waiting_time")
    async def process_time(message: Message):
        vk_id = message.from_id
        user_states[vk_id]["time"] = message.text
        user_states[vk_id]["step"] = "waiting_city"
        await message.answer("Введите город вашего рождения:")

    @bot.on.message(func=lambda msg: user_states.get(msg.from_id, {}).get("step") == "waiting_city")
    async def process_city(message: Message):
        vk_id = message.from_id
        city = message.text
        date = user_states[vk_id]["date"]
        time = user_states[vk_id]["time"]

        await create_user(vk_id, date, time, city)
        await update_user(vk_id, {"free_teaser_used": True})
        del user_states[vk_id]

        await message.answer("Анализирую данные... Ожидайте.")

        prompt = (
            f"Ты премиальный психолог-астролог. Составь короткий, интригующий тизер личности (2-3 абзаца) "
            f"по данным: дата {date}, время {time}, город {city}. "
            f"Избегай банальностей. Используй юнгианские архетипы, анализ теневой стороны. "
            f"Текст должен быть строгим, проницательным. Это лид-магнит."
        )
        teaser = await generate_text(prompt)
        if not teaser:
            teaser = "Не удалось сгенерировать тизер, но ваши данные сохранены."

        user = await get_user(vk_id)
        await message.answer(teaser, keyboard=get_dynamic_keyboard(user))

    @bot.on.message(text="Купить полный разбор")
    async def buy_full_chart(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if not user:
            await message.answer("Сначала введите свои данные. Напишите 'Начать'.")
            return

        await message.answer("Оплата прошла успешно! Генерирую полный разбор и сакральную визуальную карту... Это займет около минуты.")

        # Mark as purchased
        core_purchased_users.add(vk_id)

        date = user.get("birth_date", "неизвестно")
        time = user.get("birth_time", "неизвестно")
        city = user.get("birth_city", "неизвестно")

        text_prompt = (
            f"Ты премиальный психолог-астролог. Составь глубокий и полный анализ личности "
            f"по данным: дата {date}, время {time}, город {city}. "
            f"Избегай банальностей и ванильной астрологии. Используй юнгианские архетипы, "
            f"анализ теневой стороны личности и кармических узлов. Текст должен быть строгим, "
            f"проницательным, с долей холодного интеллекта. Пиши так, чтобы человек почувствовал "
            f"легкий шок от того, насколько точно вскрыты его скрытые мотивы."
        )
        full_text = await generate_text(text_prompt)

        image_prompt = (
            "Стиль Премиум минимализм. Темный графитовый фон, тонкие линии из матового золота. "
            "Создай абстрактную карту таро. Включи элементы строгой сакральной геометрии. "
            "Добавь легкие, едва уловимые отсылки к египетской мифологии, например, строгий профиль "
            "Анубиса или золотые весы, стилизованные под созвездия. Никакого киберпанка, глитчей или "
            "хакерских элементов. Изображение должно излучать спокойствие, роскошь и древнюю власть."
        )
        image_bytes = await generate_image(image_prompt)

        user = await get_user(vk_id)
        if full_text:
            if image_bytes:
                try:
                    uploader = PhotoMessageUploader(bot.api)
                    photo_attachment = await uploader.upload(image_bytes, peer_id=message.peer_id)
                    await message.answer(full_text, attachment=photo_attachment, keyboard=get_dynamic_keyboard(user))
                except Exception as e:
                    await message.answer(f"Текст сгенерирован, но ошибка с фото: {e}\n\n{full_text}", keyboard=get_dynamic_keyboard(user))
            else:
                await message.answer(f"Не удалось сгенерировать изображение.\n\n{full_text}", keyboard=get_dynamic_keyboard(user))
        else:
            await message.answer("Произошла ошибка при генерации разбора.")

    @bot.on.message(text="Подписка на транзиты")
    async def subscribe_transits(message: Message):
        vk_id = message.from_id
        if vk_id not in core_purchased_users:
            await message.answer("Сначала необходимо купить полный разбор.")
            return

        await update_user(vk_id, {"is_subscribed": True})
        user = await get_user(vk_id)
        await message.answer("Подписка оформлена. Теперь вы будете получать жесткий ежедневный прогноз.", keyboard=get_dynamic_keyboard(user))

    @bot.on.message(text="Проверка совместимости")
    async def check_compatibility(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if not user:
            await message.answer("Пользователь не найден.")
            return

        if vk_id not in core_purchased_users:
            await message.answer("Сначала необходимо купить полный разбор.")
            return

        balance = user.get("compatibility_balance", 0)

        if balance <= 0:
            await message.answer("Ваш баланс проверок совместимости равен 0. Пожалуйста, пополните баланс (напишите 'Пополнить').")
            return

        user_states[vk_id] = {"step": "waiting_partner_data"}
        await message.answer(f"Ваш баланс: {balance} проверок. Введите данные партнера (дата, время, город) для глубокого анализа синастрии:")

    @bot.on.message(text="Пополнить")
    async def top_up_balance(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if user:
            new_balance = user.get("compatibility_balance", 0) + 1
            await update_user(vk_id, {"compatibility_balance": new_balance})
            user = await get_user(vk_id)
            await message.answer(f"Баланс пополнен! Текущий баланс: {new_balance}", keyboard=get_dynamic_keyboard(user))
        else:
            await message.answer("Пользователь не найден.")

    @bot.on.message(func=lambda msg: user_states.get(msg.from_id, {}).get("step") == "waiting_partner_data")
    async def process_partner_data(message: Message):
        vk_id = message.from_id
        partner_data = message.text
        del user_states[vk_id]

        user = await get_user(vk_id)
        if not user:
            return

        new_balance = user.get("compatibility_balance", 0) - 1
        await update_user(vk_id, {"compatibility_balance": new_balance})

        await message.answer("Анализирую синастрию... Это займет немного времени.")
        prompt = (
            f"Ты премиальный психолог-астролог. Проведи жесткий и честный анализ совместимости "
            f"с партнером, чьи данные: {partner_data}. Используй теневые аспекты и кармические узлы."
        )
        result = await generate_text(prompt)
        if not result:
            result = "Ошибка анализа совместимости."

        user = await get_user(vk_id)
        await message.answer(f"{result}\n\nОстаток проверок совместимости: {new_balance}", keyboard=get_dynamic_keyboard(user))

    bot.loop_wrapper._running = True
    asyncio.create_task(bot.run_polling())
    
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