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

        # Базовая клавиатура - навигатор
        keyboard.add(Text("✦ Мой профиль"), color=KeyboardButtonColor.SECONDARY)

        if vk_id in core_purchased_users:
            keyboard.row()
            keyboard.add(Text("☾ Совместимость"), color=KeyboardButtonColor.SECONDARY)
            keyboard.add(Text("▱ Карта дня"), color=KeyboardButtonColor.SECONDARY)

            if not user.get("is_subscribed"):
                keyboard.row()
                keyboard.add(Text("Подписка на транзиты"), color=KeyboardButtonColor.SECONDARY)

        return keyboard.get_json()

    def get_inline_profile_keyboard() -> str:
        keyboard = Keyboard(inline=True)
        keyboard.add(Text("Пополнить баланс"), color=KeyboardButtonColor.POSITIVE)
        return keyboard.get_json()

    def get_inline_buy_full_chart() -> str:
        keyboard = Keyboard(inline=True)
        keyboard.add(Text("Купить полный разбор"), color=KeyboardButtonColor.PRIMARY)
        return keyboard.get_json()

    @bot.on.message(text=["Начать", "start", "/start"])
    async def start_handler(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if user and user.get("free_teaser_used"):
            await message.answer("СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nС возвращением.", keyboard=get_dynamic_keyboard(user))
        else:
            user_states[vk_id] = {"step": "waiting_data"}
            await message.answer("СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nУкажите дату, время и город вашего прихода в этот мир в любом удобном формате.")

    @bot.on.message(func=lambda msg: user_states.get(msg.from_id, {}).get("step") == "waiting_data")
    async def process_data(message: Message):
        vk_id = message.from_id
        await message.answer("Анализирую координаты...")

        from ai_service import extract_birth_data
        data = await extract_birth_data(message.text)

        if not data or not data.get("date") or not data.get("city"):
            await message.answer("СИСТЕМА НЕ СМОГЛА РАСПОЗНАТЬ ДАННЫЕ.\n\nПожалуйста, уточните дату, время и город.")
            return

        date = data["date"]
        time = data["time"]
        city = data["city"]

        await create_user(vk_id, date, time, city)
        await update_user(vk_id, {"free_teaser_used": True})
        del user_states[vk_id]

        prompt = (
            f"Ты премиальный психолог-астролог. Составь короткий, интригующий тизер личности (2-3 абзаца) "
            f"по данным: дата {date}, время {time}, город {city}. "
            f"Избегай банальностей. Используй юнгианские архетипы, анализ теневой стороны. "
            f"Текст должен быть строгим, проницательным. Это лид-магнит. Закончи мысль на самом интересном месте."
        )
        teaser = await generate_text(prompt)
        if not teaser:
            teaser = "ДАННЫЕ СОХРАНЕНЫ. СИСТЕМА В ОЖИДАНИИ."

        user = await get_user(vk_id)
        # Отправляем тизер с инлайн кнопкой покупки
        await message.answer(
            f"✦ ПЕРВИЧНЫЙ СРЕЗ\n\n{teaser}",
            keyboard=get_inline_buy_full_chart()
        )
        # Отправляем навигатор отдельно
        await message.answer("Используйте меню для навигации:", keyboard=get_dynamic_keyboard(user))

    @bot.on.message(text=["✦ Мой профиль", "Мой профиль"])
    async def show_profile(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if not user:
            await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
            return

        date = user.get("birth_date", "Неизвестно")
        time = user.get("birth_time", "Неизвестно")
        city = user.get("birth_city", "Неизвестно")
        balance = user.get("compatibility_balance", 0)
        sub = "Активна" if user.get("is_subscribed") else "Отсутствует"

        profile_text = (
            f"✦ ПРОФИЛЬ АСКЕТА ✦\n\n"
            f"Точка входа: {date} {time}\n"
            f"Локация: {city}\n\n"
            f"▱ Баланс синастрий: {balance}\n"
            f"▱ Подписка: {sub}"
        )
        await message.answer(profile_text, keyboard=get_inline_profile_keyboard())

    @bot.on.message(text=["Купить полный разбор", "Раскрыть полную карту"])
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

        # Генерируем выжимку для памяти (core_profile)
        if full_text:
            summary_prompt = (
                f"Сделай очень короткую выжимку (психологический профиль, 2-3 предложения) "
                f"из этого текста: {full_text[:1000]}. Это нужно для системной памяти бота."
            )
            core_profile = await generate_text(summary_prompt)
            if core_profile:
                await update_user(vk_id, {"core_profile": core_profile})

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

    @bot.on.message(text=["☾ Совместимость", "Проверка совместимости"])
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

    @bot.on.message(text=["Пополнить баланс", "Пополнить"])
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
        core_profile = user.get("core_profile", "Нет данных о пользователе.")
        prompt = (
            f"Ты премиальный психолог-астролог. Проведи жесткий и честный анализ совместимости.\n"
            f"Данные пользователя (из памяти): {core_profile}\n"
            f"Данные партнера: {partner_data}.\n"
            f"Используй теневые аспекты и кармические узлы. Отвечай жестко и прямо."
        )
        result = await generate_text(prompt)
        if not result:
            result = "Ошибка анализа совместимости."

        user = await get_user(vk_id)
        await message.answer(f"{result}\n\nОстаток проверок совместимости: {new_balance}", keyboard=get_dynamic_keyboard(user))

    @bot.on.message(text=["▱ Карта дня", "Карта дня"])
    async def draw_card_of_the_day(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if not user or vk_id not in core_purchased_users:
            await message.answer("ФУНКЦИЯ НЕДОСТУПНА.\n\nТребуется полный разбор.")
            return

        await message.answer("Колода перемешивается... Вытягиваю аркан.")

        core_profile = user.get("core_profile", "Неизвестный странник")

        # Генерация наставления
        text_prompt = (
            f"Ты Оракул. Пользователь: {core_profile}. "
            f"Вытяни одну случайную карту Таро для него на сегодняшний день. "
            f"Дай короткое (2-3 предложения), жесткое и метафоричное наставление. "
            f"Назови карту в начале (например: ✦ АРКАН: БАШНЯ ✦)."
        )
        card_text = await generate_text(text_prompt)

        # Генерация изображения карты
        image_prompt = (
            "Стиль Премиум минимализм. Темный графитовый фон, тонкие линии из матового золота. "
            "Абстрактная карта таро. Сакральная геометрия, строгие формы. "
            "Изображение должно излучать спокойствие, роскошь и древнюю власть."
        )
        image_bytes = await generate_image(image_prompt)

        if card_text and image_bytes:
            try:
                uploader = PhotoMessageUploader(bot.api)
                photo_attachment = await uploader.upload(image_bytes, peer_id=message.peer_id)
                await message.answer(card_text, attachment=photo_attachment, keyboard=get_dynamic_keyboard(user))
            except Exception as e:
                await message.answer(f"Аркан вытянут, но визуализация недоступна.\n\n{card_text}", keyboard=get_dynamic_keyboard(user))
        elif card_text:
            await message.answer(f"Визуализация недоступна.\n\n{card_text}", keyboard=get_dynamic_keyboard(user))
        else:
            await message.answer("Колода молчит. Попробуйте позже.")

    async def daily_forecast_cron():
        from database import get_all_subscribed_users
        import datetime
        while True:
            now = datetime.datetime.now()
            # Проверяем каждое утро в 9:00 (условно, можно настроить через проверку часа)
            # Для простоты демо будем делать рассылку раз в 24 часа. В продакшене тут лучше использовать библиотеку APScheduler.
            # Но так как бот работает асинхронно, сделаем простую проверку текущего часа.
            if now.hour == 9 and now.minute == 0:
                users = await get_all_subscribed_users()
                for user in users:
                    vk_id = user.get("vk_id")
                    if vk_id:
                        core_profile = user.get("core_profile", "")
                        prompt = (
                            f"Сгенерируй геймифицированный прогноз на день. "
                            f"В начале добавь шкалу энергии: 'Энергия [Случайное число 1-10]/10'. "
                            f"Укажи 'Фокус:' и 'Уязвимость:'. Опирайся на этот профиль: {core_profile}. "
                            f"Коротко, жестко."
                        )
                        forecast = await generate_text(prompt)
                        if forecast:
                            try:
                                await bot.api.messages.send(
                                    peer_id=vk_id,
                                    message=f"✦ ЕЖЕДНЕВНЫЙ ТРАНЗИТ ✦\n\n{forecast}",
                                    random_id=0
                                )
                            except Exception as e:
                                print(f"Не удалось отправить транзит {vk_id}: {e}")
                # Спим 61 минуту, чтобы не сработать дважды в 9:00
                await asyncio.sleep(3660)
            else:
                # Проверяем каждую минуту
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