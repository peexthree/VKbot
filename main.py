import ast
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    for attr in ("Num", "Str", "Bytes", "NameConstant", "Ellipsis"):
        if not hasattr(ast, attr):
            setattr(ast, attr, type(attr, (ast.Constant,), {}))

import os
import asyncio

active_tasks = set()

async def handle_ping(request):
    from aiohttp import web
    return web.Response(text="Bot is alive")

async def main():
    import aiohttp
    from aiohttp import web
    from vkbottle import Bot, Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
    from vkbottle.bot import Message
    from database import get_user, create_user, update_user, init_db, get_user_state, set_user_state
    from ai_service import generate_text, generate_image

    vk_token = os.environ.get("VK_TOKEN", "")
    bot = Bot(token=vk_token)
    
    await init_db()

    def get_dynamic_keyboard(user: dict | None) -> str:
        keyboard = Keyboard(inline=False)
        if not user:
            return keyboard.get_json()

        # Базовая клавиатура - навигатор
        keyboard.add(Text("✦ Мой профиль"), color=KeyboardButtonColor.SECONDARY)

        if user.get("has_full_chart"):
            keyboard.row()
            keyboard.add(Text("☾ Совместимость"), color=KeyboardButtonColor.SECONDARY)
            keyboard.add(Text("▱ Карта дня"), color=KeyboardButtonColor.SECONDARY)

            keyboard.row()
            keyboard.add(Text("Теневой режим"), color=KeyboardButtonColor.NEGATIVE)

            if not user.get("is_subscribed"):
                keyboard.row()
                keyboard.add(Text("Подписка на транзиты"), color=KeyboardButtonColor.SECONDARY)
        elif not user.get("free_card_used", False):
            keyboard.row()
            keyboard.add(Text("▱ Карта дня (Демо)"), color=KeyboardButtonColor.SECONDARY)

        return keyboard.get_json()

    def get_inline_profile_keyboard() -> str:
        keyboard = Keyboard(inline=True)
        keyboard.add(Text("Пополнить баланс"), color=KeyboardButtonColor.POSITIVE)
        return keyboard.get_json()

    import uuid
    async def create_yookassa_payment(amount: int, description: str, user_id: int, section: str, host: str) -> str:
        shop_id = os.environ.get("YOOKASSA_SHOP_ID")
        secret_key = os.environ.get("YOOKASSA_SECRET_KEY")
        if not shop_id or not secret_key:
            return f"{host}/payment/webhook?user_id={user_id}&amount={amount}&section={section}&secret=dummy_secret_123"

        import aiohttp
        url = "https://api.yookassa.ru/v3/payments"
        auth = aiohttp.BasicAuth(shop_id, secret_key)
        headers = {
            "Idempotence-Key": str(uuid.uuid4()),
            "Content-Type": "application/json"
        }
        payload = {
            "amount": {
                "value": f"{amount}.00",
                "currency": "RUB"
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": "https://vk.com/"
            },
            "description": description,
            "metadata": {
                "user_id": str(user_id),
                "section": section
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, auth=auth) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["confirmation"]["confirmation_url"]
                else:
                    return f"{host}/payment/webhook?user_id={user_id}&amount={amount}&section={section}&secret=dummy_secret_123"

    async def get_sections_keyboard(user_id: int, user: dict | None) -> str:
        from vkbottle import OpenLink
        keyboard = Keyboard(inline=True)
        port = os.environ.get("PORT", 10000)
        host = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")

        purchased = user.get("purchased_sections", {}) if user else {}

        # Секс
        if purchased.get("sex"):
            keyboard.add(Text("✦ СЕКС (Открыто)"), color=KeyboardButtonColor.POSITIVE)
        else:
            pay_url = await create_yookassa_payment(99, "СЕКС", user_id, "sex", host)
            keyboard.add(OpenLink(pay_url, "✦ СЕКС за 99р"))
        keyboard.row()

        # Деньги
        if purchased.get("money"):
            keyboard.add(Text("✦ ДЕНЬГИ (Открыто)"), color=KeyboardButtonColor.POSITIVE)
        else:
            pay_url = await create_yookassa_payment(99, "ДЕНЬГИ", user_id, "money", host)
            keyboard.add(OpenLink(pay_url, "✦ ДЕНЬГИ за 99р"))
        keyboard.row()

        # Тень
        if purchased.get("shadow"):
            keyboard.add(Text("✦ ТЕНЬ (Открыто)"), color=KeyboardButtonColor.POSITIVE)
        else:
            pay_url = await create_yookassa_payment(99, "ТЕНЬ", user_id, "shadow", host)
            keyboard.add(OpenLink(pay_url, "✦ ТЕНЬ за 99р"))
        keyboard.row()

        # Финал
        if purchased.get("final"):
            keyboard.add(Text("✦ ФИНАЛ (Открыто)"), color=KeyboardButtonColor.POSITIVE)
        else:
            pay_url = await create_yookassa_payment(99, "ФИНАЛ", user_id, "final", host)
            keyboard.add(OpenLink(pay_url, "✦ ФИНАЛ за 99р"))

        # Кнопка бандла, если не все куплено
        if not all([purchased.get("sex"), purchased.get("money"), purchased.get("shadow"), purchased.get("final")]):
            keyboard.row()
            pay_url_all = await create_yookassa_payment(399, "ОТКРЫТЬ ВСЁ", user_id, "all", host)
            keyboard.add(OpenLink(pay_url_all, "✦ ОТКРЫТЬ ВСЁ ЗА 399р"))

        return keyboard.get_json()

    @bot.on.message(text=["Начать", "start", "/start"])
    async def start_handler(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            user = await get_user(vk_id)
            if user and user.get("free_teaser_used"):
                await message.answer("СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nС возвращением.", keyboard=get_dynamic_keyboard(user))
            else:
                if not user:
                    await create_user(vk_id, "", "", "")
                import json
                await set_user_state(vk_id, json.dumps({"step": "date"}))

                await message.answer(
                    "СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nУкажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):"
                )
        finally:
            active_tasks.discard(vk_id)

    async def get_fsm_step(vk_id: int) -> dict | None:
        state = await get_user_state(vk_id)
        if not state:
            return None
        try:
            import json
            return json.loads(state)
        except:
            if state == "registration":
                return {"step": "date"}
            return None

    async def is_waiting_date(message: Message) -> bool:
        if message.text and message.text.lower() in ["начать", "start", "/start"]:
            return False
        state_dict = await get_fsm_step(message.from_id)
        return state_dict is not None and state_dict.get("step") == "date"

    @bot.on.message(func=is_waiting_date)
    async def process_date(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            date_str = message.text.strip()

            # В реальном проекте тут нужна валидация даты
            import json
            await set_user_state(vk_id, json.dumps({"step": "time", "date": date_str}))

            kb = Keyboard(inline=True)
            kb.add(Text("Не знаю время (12:00)"), color=KeyboardButtonColor.SECONDARY)
            await message.answer("Укажите ВРЕМЯ рождения (например, 14:30):", keyboard=kb.get_json())
        finally:
            active_tasks.discard(vk_id)

    async def is_waiting_time(message: Message) -> bool:
        if message.text and message.text.lower() in ["начать", "start", "/start"]:
            return False
        state_dict = await get_fsm_step(message.from_id)
        return state_dict is not None and state_dict.get("step") == "time"

    @bot.on.message(func=is_waiting_time)
    async def process_time(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            time_str = message.text.strip()
            if time_str.lower() == "не знаю время" or time_str.lower() == "не знаю время (12:00)":
                time_str = "12:00"

            state_dict = await get_fsm_step(vk_id)
            date_str = state_dict.get("date", "")

            import json
            await set_user_state(vk_id, json.dumps({"step": "city", "date": date_str, "time": time_str}))

            await message.answer("Укажите ГОРОД рождения:")
        finally:
            active_tasks.discard(vk_id)

    async def is_waiting_city(message: Message) -> bool:
        if message.text and message.text.lower() in ["начать", "start", "/start"]:
            return False
        state_dict = await get_fsm_step(message.from_id)
        return state_dict is not None and state_dict.get("step") == "city"

    @bot.on.message(func=is_waiting_city)
    async def process_city(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            city_str = message.text.strip()
            state_dict = await get_fsm_step(vk_id)

            date = state_dict.get("date", "")
            time = state_dict.get("time", "")
            city = city_str

            await message.answer("Анализирую координаты...")
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

            user = await update_user(vk_id, {
                "birth_date": date,
                "birth_time": time,
                "birth_city": city,
                "free_teaser_used": True
            })
            if not user:
                await message.answer("СИСТЕМА ДАЛА СБОЙ. Не удалось сохранить данные. Повторите попытку.")
                return

            await set_user_state(vk_id, "")

            from ai_service import generate_section
            base_text = await generate_section("base", date, time, city)
            if not base_text:
                base_text = "ДАННЫЕ СОХРАНЕНЫ. СИСТЕМА В ОЖИДАНИИ."

            user = await get_user(vk_id)
            # Отправляем базу с кнопками покупки остальных разделов
            kb_json = await get_sections_keyboard(vk_id, user)
            await message.answer(
                f"✦ БАЗА ✦\n\n{base_text}",
                keyboard=kb_json
            )
            # Отправляем навигатор отдельно
            await message.answer("Используйте меню для навигации:", keyboard=get_dynamic_keyboard(user))

        finally:
            active_tasks.discard(vk_id)

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

    async def process_payment_and_generate(vk_id: int, section: str):
        if vk_id in active_tasks:
            return
        user = await get_user(vk_id)
        if not user:
            return

        active_tasks.add(vk_id)
        try:
            # Mark as purchased in database
            purchased = user.get("purchased_sections", {})
            if section == "all":
                purchased = {"sex": True, "money": True, "shadow": True, "final": True}
                await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})
                await bot.api.messages.send(peer_id=vk_id, message="ОПЛАТА УСПЕШНА.\n\nВсе Врата открыты.", random_id=0)
            elif section in purchased:
                purchased[section] = True
                updates = {"purchased_sections": purchased}
                if all(purchased.values()):
                    updates["has_full_chart"] = True
                await update_user(vk_id, updates)
                await bot.api.messages.send(peer_id=vk_id, message="ОПЛАТА УСПЕШНА.\n\nРаздел открыт.", random_id=0)

            user = await get_user(vk_id)
            kb_json = await get_sections_keyboard(vk_id, user)
            await bot.api.messages.send(
                peer_id=vk_id,
                message="Используйте меню для вызова нужного раздела:",
                keyboard=kb_json,
                random_id=0
            )

        finally:
            active_tasks.discard(vk_id)

    @bot.on.message(text=["✦ СЕКС (Открыто)", "✦ ДЕНЬГИ (Открыто)", "✦ ТЕНЬ (Открыто)", "✦ ФИНАЛ (Открыто)"])
    async def handle_section_request(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        user = await get_user(vk_id)
        if not user:
            return

        purchased = user.get("purchased_sections", {})
        text_lower = message.text.lower()

        section_map = {
            "секс": "sex",
            "деньги": "money",
            "тень": "shadow",
            "финал": "final"
        }

        target_section = None
        for key in section_map:
            if key in text_lower:
                target_section = section_map[key]
                break

        if not target_section or not purchased.get(target_section):
            return

        active_tasks.add(vk_id)
        try:
            await bot.api.messages.set_activity(peer_id=vk_id, type="typing")

            date = user.get("birth_date", "неизвестно")
            time = user.get("birth_time", "неизвестно")
            city = user.get("birth_city", "неизвестно")

            from ai_service import generate_section
            result_text = await generate_section(target_section, date, time, city)

            if not result_text:
                kb_json = await get_sections_keyboard(vk_id, user)
                await message.answer("Ошибка генерации.", keyboard=kb_json)
                return

            if target_section == "final":
                import re
                match = re.search(r"ID_ТАРО:\s*(\d+)", result_text)
                card_id = "0"
                if match:
                    num = int(match.group(1))
                    if 0 <= num <= 77:
                        card_id = str(num)

                # Fetch image from github
                image_url = f"https://raw.githubusercontent.com/cyber-olesya/tarot-cards/main/cards/{card_id}.png"
                image_bytes = None
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                except Exception as e:
                    print(f"Failed to fetch tarot card {card_id}: {e}")

                if image_bytes:
                    try:
                        from vkbottle import PhotoMessageUploader
                        uploader = PhotoMessageUploader(bot.api)
                        photo_attachment = await uploader.upload(image_bytes, peer_id=vk_id)
                        kb_json = await get_sections_keyboard(vk_id, user)
                        await message.answer(result_text, attachment=photo_attachment, keyboard=kb_json)
                    except Exception as e:
                        kb_json = await get_sections_keyboard(vk_id, user)
                        await message.answer(f"Текст сгенерирован, но ошибка с фото: {e}\n\n{result_text}", keyboard=kb_json)
                else:
                    kb_json = await get_sections_keyboard(vk_id, user)
                    await message.answer(f"{result_text}", keyboard=kb_json)

                # Generate summary for memory
                from ai_service import generate_text
                summary_prompt = (
                    f"Сделай очень короткую выжимку (психологический профиль, 2-3 предложения) "
                    f"из этого текста: {result_text[:1000]}. Это нужно для системной памяти бота."
                )
                core_profile = await generate_text(summary_prompt)
                if core_profile:
                    await update_user(vk_id, {"core_profile": core_profile})
            else:
                kb_json = await get_sections_keyboard(vk_id, user)
                await message.answer(result_text, keyboard=kb_json)

        finally:
            active_tasks.discard(vk_id)

    @bot.on.message(text="Подписка на транзиты")
    async def subscribe_transits(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if not user or not user.get("has_full_chart"):
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

        if not user.get("has_full_chart"):
            await message.answer("Сначала необходимо купить полный разбор.")
            return

        balance = user.get("compatibility_balance", 0)

        if balance <= 0:
            await message.answer("Ваш баланс проверок совместимости равен 0. Пожалуйста, пополните баланс (напишите 'Пополнить').")
            return

        await set_user_state(vk_id, "waiting_partner_data")
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

    async def is_waiting_partner_data(message: Message) -> bool:
        if message.text and message.text.lower() in ["начать", "start", "/start"]:
            return False
        state = await get_user_state(message.from_id)
        return state == "waiting_partner_data"

    @bot.on.message(func=is_waiting_partner_data)
    async def process_partner_data(message: Message):
        vk_id = message.from_id

        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            partner_data = message.text

            user = await get_user(vk_id)
            if not user:
                return

            new_balance = user.get("compatibility_balance", 0) - 1
            await update_user(vk_id, {
                "compatibility_balance": new_balance
            })
            await set_user_state(vk_id, "")

            await message.answer("Анализирую синастрию... Это займет немного времени.")
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

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

        finally:
            active_tasks.discard(vk_id)

    @bot.on.message(text=["▱ Карта дня", "Карта дня", "▱ Карта дня (Демо)"])
    async def draw_card_of_the_day(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            user = await get_user(vk_id)
            if not user:
                return

            is_demo = not user.get("has_full_chart")
            if is_demo:
                if user.get("free_card_used"):
                    await message.answer("ДЕМО ИСЧЕРПАНО.\n\nДля продолжения работы с Оракулом требуется полный разбор.")
                    return
                await update_user(vk_id, {"free_card_used": True})
                user = await get_user(vk_id) # Refresh to update keyboard

            await message.answer("Колода перемешивается... Вытягиваю аркан.")
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

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

        finally:
            active_tasks.discard(vk_id)

    @bot.on.message(text="Теневой режим")
    async def toggle_shadow_mode(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks: return
        active_tasks.add(vk_id)
        try:
            user = await get_user(vk_id)
            if not user or not user.get("has_full_chart"):
                await message.answer("ФУНКЦИЯ НЕДОСТУПНА.\n\nТребуется полный разбор.")
                return

            await message.answer("Активирую Теневой режим...")
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

            core_profile = user.get("core_profile", "Неизвестный странник")
            text_prompt = (
                f"Ты Злой Оракул. Прочитай профиль этого человека: {core_profile}. "
                f"Выдай ему одну короткую, крайне жесткую и неприятную правду о нем. "
                f"Никакого позитива или надежды. Только обнаженная тьма его личности."
            )
            shadow_text = await generate_text(text_prompt)
            if shadow_text:
                await message.answer(f"✦ ТЕНЕВОЙ РЕЖИМ ✦\n\n{shadow_text}")
                # Голосовое сообщение для пущего эффекта (Киллер-фича)
                from ai_service import generate_audio_prediction
                from vkbottle import AudioMessageUploader
                audio_bytes = await generate_audio_prediction(shadow_text)
                if audio_bytes and audio_bytes != b"dummy_audio_data":
                    # Заглушка: в реальном мире загружаем войс через AudioMessageUploader
                    pass
            else:
                await message.answer("Тень молчит. Попробуйте позже.")
        finally:
            active_tasks.discard(vk_id)

    async def daily_forecast_cron():
        from database import get_all_subscribed_users, get_inactive_free_users
        import datetime
        while True:
            now = datetime.datetime.now()
            # Проверяем каждое утро в 9:00
            if now.hour == 9 and now.minute == 0:
                # 1. Отправляем прогнозы подписчикам
                users = await get_all_subscribed_users()

                async def send_forecast(user):
                    vk_id = user.get("vk_id")
                    if not vk_id: return
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

                # Запускаем батчами (gather) с ограничением на 5 одновременных запросов
                sem = asyncio.Semaphore(5)
                async def sem_send_forecast(u):
                    async with sem:
                        await send_forecast(u)

                await asyncio.gather(*(sem_send_forecast(u) for u in users))

                # 2. Кармические пуши: Напоминаем бесплатникам
                inactive_users = await get_inactive_free_users()
                for user in inactive_users:
                    vk_id = user.get("vk_id")
                    if vk_id and user.get("free_teaser_used"):
                        try:
                            kb = get_inline_buy_full_chart(vk_id)
                            await bot.api.messages.send(
                                peer_id=vk_id,
                                message="Теневой аспект активен. Вы игнорируете свою суть. Ваш профиль меркнет.\n\nПродолжите работу с Оракулом, чтобы получить ответы.",
                                keyboard=kb,
                                random_id=0
                            )
                        except Exception as e:
                            pass

                # Спим 61 минуту, чтобы не сработать дважды
                await asyncio.sleep(3660)
            else:
                await asyncio.sleep(60)

    bot.loop_wrapper._running = True
    asyncio.create_task(bot.run_polling())
    asyncio.create_task(daily_forecast_cron())
    
    async def payment_webhook(request):
        try:
            import json
            user_id_str = None
            section = None

            if request.method == "POST":
                try:
                    data = await request.json()
                    # YooKassa webhook format
                    if data.get("event") == "payment.succeeded":
                        metadata = data.get("object", {}).get("metadata", {})
                        user_id_str = metadata.get("user_id")
                        section = metadata.get("section")
                except json.JSONDecodeError:
                    # fallback for dummy form post
                    data = await request.post()
                    user_id_str = data.get('user_id')
                    section = data.get('section')
            else:
                data = request.query
                user_id_str = data.get('user_id')
                section = data.get('section')

            if not user_id_str or not section:
                return web.Response(text="Missing user_id or section", status=400)
            user_id = int(user_id_str)
            print("Платеж получен")

            # Fire and forget the processing
            asyncio.create_task(process_payment_and_generate(user_id, section))

            return web.Response(text="Payment processed successfully! You can close this window and return to the bot.")
        except Exception as e:
            return web.Response(text=str(e), status=500)

    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_route('*', '/payment/webhook', payment_webhook)
    
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