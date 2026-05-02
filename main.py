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
    from vkbottle import Bot, Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader, GroupEventType
    from vkbottle.bot import Message
    from database import get_user, create_user, update_user, init_db, get_user_state, set_user_state
    from ai_service import generate_text

    vk_token = os.environ.get("VK_TOKEN", "")
    bot = Bot(token=vk_token)
    
    await init_db()

    def get_dynamic_keyboard(user: dict | None) -> str:
        keyboard = Keyboard(inline=False)
        if not user:
            return keyboard.get_json()

        # Базовая клавиатура - навигатор
        keyboard.add(Text("✦ Мой профиль"), color=KeyboardButtonColor.SECONDARY)

        return keyboard.get_json()

    def get_inline_profile_keyboard(user: dict | None) -> str:
        import json

        purchased = user.get("purchased_sections", {}) if user else {}

        buttons = []

        # Секс
        if not purchased.get("sex"):
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=100"}}])

        # Деньги
        if not purchased.get("money"):
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=90"}}])

        # Тень
        if not purchased.get("shadow"):
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=70"}}])

        # Финал
        if not purchased.get("final"):
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=120"}}])

        # Бандл: если куплено меньше двух разделов
        purchased_count = sum([bool(purchased.get("sex")), bool(purchased.get("money")), bool(purchased.get("shadow")), bool(purchased.get("final"))])
        if purchased_count < 2:
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=300"}}])

        # Кнопка возврата в меню
        buttons.append([{"action": {"type": "text", "label": "В ГЛАВНОЕ МЕНЮ"}, "color": "primary"}])

        keyboard_obj = {
            "inline": True,
            "buttons": buttons
        }

        return json.dumps(keyboard_obj, ensure_ascii=False)

    async def get_sections_keyboard(user_id: int, user: dict | None) -> str:
        import json

        purchased = user.get("purchased_sections", {}) if user else {}

        buttons = []

        # Секс
        if purchased.get("sex"):
            buttons.append([{"action": {"type": "text", "label": "✦ СЕКС (Открыто)"}, "color": "positive"}])
        else:
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=100"}}])

        # Деньги
        if purchased.get("money"):
            buttons.append([{"action": {"type": "text", "label": "✦ ДЕНЬГИ (Открыто)"}, "color": "positive"}])
        else:
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=90"}}])

        # Тень
        if purchased.get("shadow"):
            buttons.append([{"action": {"type": "text", "label": "✦ ТЕНЬ (Открыто)"}, "color": "positive"}])
        else:
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=70"}}])

        # Финал
        if purchased.get("final"):
            buttons.append([{"action": {"type": "text", "label": "✦ ФИНАЛ (Открыто)"}, "color": "positive"}])
        else:
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=120"}}])

        # Кнопка бандла, если не все куплено
        if not all([purchased.get("sex"), purchased.get("money"), purchased.get("shadow"), purchased.get("final")]):
            buttons.append([{"action": {"type": "vkpay", "hash": "action=transfer-to-group&group_id=219181948&amount=300"}}])

        keyboard_obj = {
            "inline": True,
            "buttons": buttons
        }

        return json.dumps(keyboard_obj, ensure_ascii=False)

    @bot.on.message(text=["Начать", "start", "/start"])
    async def start_handler(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            user = await get_user(vk_id)

            # 1. Если данные уже есть (дата, время, город) - прыгаем сразу в главное меню
            if user and user.get("birth_date") and user.get("birth_time") and user.get("birth_city"):
                purchased = user.get("purchased_sections", {})
                first_name = purchased.get("first_name", "")
                greeting = f"С возвращением, {first_name}." if first_name else "С возвращением."
                await message.answer(f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\n{greeting}", keyboard=get_dynamic_keyboard(user))
                return

            # 2. Получаем данные из VK
            first_name = ""
            sex = 0
            bdate = ""
            city = ""
            try:
                users_info = await bot.api.users.get(user_ids=[vk_id], fields=["sex", "bdate", "city"])
                if users_info:
                    info = users_info[0]
                    first_name = info.first_name
                    sex = info.sex
                    bdate = info.bdate if info.bdate else ""
                    if info.city:
                        city = info.city.title
            except Exception as e:
                print(f"Error fetching user info: {e}")

            if not user:
                user = await create_user(vk_id, "", "", "")

            if user:
                # Store first_name and sex in purchased_sections jsonb field
                purchased = user.get("purchased_sections", {})
                purchased["first_name"] = first_name
                purchased["sex"] = sex
                await update_user(vk_id, {"purchased_sections": purchased})

            import json
            # Если вк вернул bdate (в формате D.M.YYYY) и город
            if bdate and city:
                await set_user_state(vk_id, json.dumps({"step": "time", "date": bdate, "city": city}))
                kb = Keyboard(inline=True)
                kb.add(Text("Не знаю время (12:00)"), color=KeyboardButtonColor.SECONDARY)
                await message.answer(
                    f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nПривет, {first_name}. Твой город ({city}) и дата рождения ({bdate}) загружены.\n"
                    "Укажите ВРЕМЯ рождения (например, 14:30):", keyboard=kb.get_json()
                )
            elif bdate:
                await set_user_state(vk_id, json.dumps({"step": "time", "date": bdate}))
                kb = Keyboard(inline=True)
                kb.add(Text("Не знаю время (12:00)"), color=KeyboardButtonColor.SECONDARY)
                await message.answer(
                    f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nПривет, {first_name}. Твоя дата рождения ({bdate}) загружена.\n"
                    "Укажите ВРЕМЯ рождения (например, 14:30):", keyboard=kb.get_json()
                )
            elif city:
                await set_user_state(vk_id, json.dumps({"step": "date", "city": city}))
                await message.answer(
                    f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nПривет, {first_name}. Твой город ({city}) загружен.\n"
                    "Укажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):"
                )
            else:
                await set_user_state(vk_id, json.dumps({"step": "date"}))
                greeting = f"Привет, {first_name}." if first_name else "Привет."
                await message.answer(
                    f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\n{greeting}\n"
                    "Укажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):"
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
            city_str_existing = state_dict.get("city", "")

            import json

            # If we already got the city from VK, we can skip process_city
            if city_str_existing:
                await message.answer("Анализирую координаты...")
                await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

                user = await update_user(vk_id, {
                    "birth_date": date_str,
                    "birth_time": time_str,
                    "birth_city": city_str_existing
                })
                await set_user_state(vk_id, "")

                if not user:
                    user = await get_user(vk_id)

                purchased = user.get("purchased_sections", {}) if user else {}
                first_name = purchased.get("first_name", "")

                from ai_service import generate_section
                base_text = await generate_section("base", date_str, time_str, city_str_existing)

                if base_text:
                    if first_name:
                        base_text = f"{first_name},\n\n" + base_text
                    kb_json = await get_sections_keyboard(vk_id, user)
                    try:
                        await message.answer(
                            base_text,
                            keyboard=kb_json
                        )
                    except Exception as e:
                        print(f"Error sending message with keyboard in process_time: {e}")
                        try:
                            # Fallback without keyboard
                            await message.answer(base_text)
                        except Exception as e_fallback:
                            print(f"Fallback send failed in process_time: {e_fallback}")
                else:
                    try:
                        await message.answer("Используйте меню для навигации:", keyboard=get_dynamic_keyboard(user))
                    except Exception as e:
                        print(f"Error sending navigation menu: {e}")
            else:
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

            # Мгновенный коммит
            user = await update_user(vk_id, {
                "birth_date": date,
                "birth_time": time,
                "birth_city": city
            })
            if not user:
                await message.answer("СИСТЕМА ДАЛА СБОЙ. Не удалось сохранить данные в базу. Повторите попытку позже.")
                return

            # Очистка состояния
            await set_user_state(vk_id, "")

            user = await get_user(vk_id)
            purchased = user.get("purchased_sections", {}) if user else {}
            first_name = purchased.get("first_name", "")

            from ai_service import generate_section
            core_profile = user.get("core_profile", "")
            base_text = await generate_section("base", date, time, city, core_profile)

            if base_text:
                if first_name:
                    base_text = f"{first_name},\n\n" + base_text
            else:
                base_text = "ДАННЫЕ СОХРАНЕНЫ. СИСТЕМА В ОЖИДАНИИ."

            # Отправляем базу с кнопками покупки остальных разделов
            kb_json = await get_sections_keyboard(vk_id, user)
            try:
                await message.answer(
                    f"✦ БАЗА ✦\n\n{base_text}",
                    keyboard=kb_json
                )
            except Exception as e:
                print(f"Error sending message with keyboard in process_city: {e}")
                try:
                    await message.answer(f"✦ БАЗА ✦\n\n{base_text}")
                except Exception as e_fallback:
                    print(f"Fallback send failed in process_city: {e_fallback}")
            # Отправляем навигатор отдельно
            try:
                await message.answer("Используйте меню для навигации:", keyboard=get_dynamic_keyboard(user))
            except Exception as e:
                print(f"Error sending navigation menu in process_city: {e}")

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
        purchased = user.get("purchased_sections", {})
        first_name = purchased.get("first_name", "")

        name_line = f"ИМЯ: {first_name}\n" if first_name else ""

        # Генерируем прайс-лист для некупленных разделов
        price_list = []
        if not purchased.get("sex"):
            price_list.append("ГРЯЗНЫЕ СЕКРЕТЫ (СЕКС) - 100 РУБ")
        if not purchased.get("money"):
            price_list.append("МАГНИТ ДЛЯ КРИПТЫ (ДЕНЬГИ) - 90 РУБ")
        if not purchased.get("shadow"):
            price_list.append("ТЕМНЫЕ ДЕМОНЫ (ТЕНЬ) - 70 РУБ")
        if not purchased.get("final"):
            price_list.append("ПОЛНЫЙ РАСКЛАД (ФИНАЛ) - 120 РУБ")

        purchased_count = sum([bool(purchased.get("sex")), bool(purchased.get("money")), bool(purchased.get("shadow")), bool(purchased.get("final"))])
        if purchased_count < 2:
            price_list.append("ВЕСЬ ПАКЕТ СУДЬБЫ - 300 РУБ")

        price_text = "\n\n" + "\n\n".join(price_list) if price_list else ""

        profile_text = (
            f"✦ ПРОФИЛЬ АСКЕТА ✦\n\n"
            f"{name_line}ТОЧКА ВХОДА: {date} {time}\n"
            f"ЛОКАЦИЯ: {city}"
            f"{price_text}"
        )
        await message.answer(profile_text, keyboard=get_inline_profile_keyboard(user))


    @bot.on.raw_event(GroupEventType.VKPAY_TRANSACTION, dataclass=dict)
    async def money_transfer_handler(event: dict):
        try:
            group_id = event.get("group_id")
            if group_id != 219181948:
                return

            # VK API typically sends event within an object depending on the exact callback format
            # In message_event or money_transfer, we can extract from_id and amount
            obj = event.get("object", {})
            vk_id = obj.get("from_id")
            amount = obj.get("amount")

            if not vk_id or not amount:
                return

            # amount is in kopecks or rubles? standard money_transfer is rubles usually, but if kopecks it's amount / 100
            # Let's check amount string or integer. In VK it's typically an integer amount.
            # Assuming 99 or 399

            amount_val = int(amount)
            if amount_val > 1000: # if it's in kopecks like 9900
                amount_val = amount_val // 100

            section = "unknown"
            if amount_val == 100:
                section = "sex"
            elif amount_val == 90:
                section = "money"
            elif amount_val == 70:
                section = "shadow"
            elif amount_val == 120:
                section = "final"
            elif amount_val == 300:
                section = "all"

            if section == "unknown":
                print(f"НЕИЗВЕСТНЫЙ ПЛАТЕЖ: vk_id={vk_id}, amount={amount_val}")
                return

            await process_payment_and_generate(vk_id, section)
        except Exception as e:
            print(f"Error handling money_transfer: {e}")

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
                purchased["sex"] = True
                purchased["money"] = True
                purchased["shadow"] = True
                purchased["final"] = True
                await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})
                await bot.api.messages.send(peer_id=vk_id, message="ОПЛАТА УСПЕШНА.\n\nВсе Врата открыты.", random_id=0)
            elif section in ["sex", "money", "shadow", "final"]:
                purchased[section] = True
                updates = {"purchased_sections": purchased}

                # Check if all four main sections are purchased
                if purchased.get("sex") and purchased.get("money") and purchased.get("shadow") and purchased.get("final"):
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

    @bot.on.message(text=["В ГЛАВНОЕ МЕНЮ", "МЕНЮ", "НАЗАД"])
    async def back_to_main_menu(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        user = await get_user(vk_id)
        if not user:
            await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
            return

        active_tasks.add(vk_id)
        try:
            kb_json = await get_sections_keyboard(vk_id, user)
            await message.answer(
                "ТВОИ ДАННЫЕ В СИСТЕМЕ. КУДА ДВИНЕМСЯ ДАЛЬШЕ?",
                keyboard=kb_json
            )
        except Exception as e:
            print(f"Error sending main menu: {e}")
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
            first_name = purchased.get("first_name", "")

            from ai_service import generate_section
            core_profile = user.get("core_profile", "")
            result_text = await generate_section(target_section, date, time, city, core_profile)

            if not result_text:
                kb_json = await get_sections_keyboard(vk_id, user)
                await message.answer("Ошибка генерации.", keyboard=kb_json)
                return

            if first_name:
                result_text = f"{first_name},\n\n" + result_text

            if target_section in ["sex", "money", "shadow", "final"]:
                import re
                match = re.search(r"ID_ТАРО:\s*(\d+)", result_text)
                card_id = "0"
                if match:
                    num = int(match.group(1))
                    if 0 <= num <= 77:
                        card_id = str(num)

                # Fetch image from github
                image_url = f"https://raw.githubusercontent.com/peexthree/VKbot/main/cards/{card_id}.jpeg"
                image_bytes = None
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                except Exception as e:
                    print(f"Failed to fetch tarot card {card_id}: {e}")

                # Убираем техническую строку с ID_ТАРО из финального текста
                display_text = re.sub(r"ID_ТАРО:\s*\d+", "", result_text).strip()

                if image_bytes:
                    try:
                        from vkbottle import PhotoMessageUploader
                        uploader = PhotoMessageUploader(bot.api)
                        photo_attachment = await uploader.upload(image_bytes, peer_id=vk_id)
                        kb_json = await get_sections_keyboard(vk_id, user)
                        try:
                            await message.answer(display_text, attachment=photo_attachment, keyboard=kb_json)
                        except Exception as inner_e:
                            print(f"Error sending message with attachment and keyboard: {inner_e}")
                            await message.answer(display_text, attachment=photo_attachment)
                    except Exception as e:
                        kb_json = await get_sections_keyboard(vk_id, user)
                        try:
                            await message.answer(f"Текст сгенерирован, но ошибка с фото: {e}\n\n{display_text}", keyboard=kb_json)
                        except Exception as inner_e2:
                            print(f"Error sending message with error text and keyboard: {inner_e2}")
                            await message.answer(f"Текст сгенерирован, но ошибка с фото: {e}\n\n{display_text}")
                else:
                    kb_json = await get_sections_keyboard(vk_id, user)
                    try:
                        await message.answer(f"{display_text}", keyboard=kb_json)
                    except Exception as e:
                        print(f"Error sending display text with keyboard: {e}")
                        await message.answer(f"{display_text}")

                if target_section == "final":
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
                try:
                    await message.answer(result_text, keyboard=kb_json)
                except Exception as e:
                    print(f"Error sending text with keyboard: {e}")
                    await message.answer(result_text)

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
                    if vk_id and user.get("birth_city"):
                        try:
                            # Для кармических пушей мы можем отправить ссылку на оплату
                            # или просто текст, так как get_inline_buy_full_chart больше нет
                            await bot.api.messages.send(
                                peer_id=vk_id,
                                message="Теневой аспект активен. Вы игнорируете свою суть. Ваш профиль меркнет.\n\nПродолжите работу с Оракулом, чтобы получить ответы.",
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