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
    
    cover_cache = {}

    async def get_cover_photo_id(cover_name: str) -> str:
        if cover_name in cover_cache:
            return cover_cache[cover_name]
        try:
            uploader = PhotoMessageUploader(bot.api)
            url = f"https://raw.githubusercontent.com/peexthree/VKbot/main/cards/{cover_name}"
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        raw_photo_id = await uploader.upload(data)

                        cover_cache[cover_name] = raw_photo_id
                        return raw_photo_id
                    else:
                        print(f"Failed to fetch cover {cover_name}: {resp.status}")
        except Exception as e:
            print(f"Failed to upload cover {cover_name}: {e}")
        return ""

    await init_db()

    def get_dynamic_keyboard(user: dict | None) -> str:
        keyboard = Keyboard(inline=False)
        if not user:
            return keyboard.get_json()

        # Базовая клавиатура - навигатор
        keyboard.add(Text("✦ Мой профиль"), color=KeyboardButtonColor.SECONDARY)
        keyboard.add(Text("✦ Главное меню"), color=KeyboardButtonColor.PRIMARY)
        keyboard.row()
        keyboard.add(Text("✦ Баланс"), color=KeyboardButtonColor.SECONDARY)
        keyboard.add(Text("✦ Услуги"), color=KeyboardButtonColor.SECONDARY)

        return keyboard.get_json()



    async def get_sections_keyboard(user_id: int, user: dict | None) -> str:
        import json

        purchased = user.get("purchased_sections", {}) if user else {}

        buttons = []

        # Секс
        if purchased.get("sex"):
            buttons.append([{"action": {"type": "text", "label": "✦ СЕКС (Открыто)"}, "color": "positive"}])

        # Деньги
        if purchased.get("money"):
            buttons.append([{"action": {"type": "text", "label": "✦ ДЕНЬГИ (Открыто)"}, "color": "positive"}])

        # Тень
        if purchased.get("shadow"):
            buttons.append([{"action": {"type": "text", "label": "✦ ТЕНЬ (Открыто)"}, "color": "positive"}])

        # Финал
        if purchased.get("final"):
            buttons.append([{"action": {"type": "text", "label": "✦ ФИНАЛ (Открыто)"}, "color": "positive"}])

        if not buttons:
            buttons.append([{"action": {"type": "text", "label": "✦ Услуги"}, "color": "secondary"}])

        keyboard_obj = {
            "inline": True,
            "buttons": buttons
        }

        return json.dumps(keyboard_obj, ensure_ascii=False)
    @bot.on.message(text=["СБРОС"])
    async def reset_user_handler(message: Message):
        vk_id = message.from_id
        
        # 1. Полностью обнуляем поля регистрации в БД
        await update_user(vk_id, {
            "birth_date": "",
            "birth_time": "",
            "birth_city": "",
            "purchased_sections": {},
            "core_profile": ""
        })
        
        # 2. Очищаем состояние FSM
        await set_user_state(vk_id, "")
        
        await message.answer("СИСТЕМА ОБНУЛЕНА. ТЫ ДЛЯ МЕНЯ ТЕПЕРЬ НИКТО. Напиши 'Начать' для теста с нуля.")
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
                purchased["sex_val"] = sex # Avoid overwriting the "sex" purchased section key
                await update_user(vk_id, {"purchased_sections": purchased})

            import json
            # Если вк вернул bdate (в формате D.M.YYYY) и город
            if bdate and city:
                await set_user_state(vk_id, json.dumps({"step": "confirm_data", "date": bdate, "city": city}))
                kb = Keyboard(inline=True)
                kb.add(Text("ВЕРНО"), color=KeyboardButtonColor.POSITIVE)
                kb.add(Text("ИЗМЕНИТЬ"), color=KeyboardButtonColor.NEGATIVE)
                await message.answer(
                    f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nПривет, {first_name}.\n"
                    f"ТВОЙ ГОРОД - {city}, ДАТА РОЖДЕНИЯ - {bdate}. ЭТИ ДАННЫЕ ВЕРНЫ? СИСТЕМА НЕ ПРОЩАЕТ ОШИБОК ПРИ РАСЧЕТЕ СУДЬБЫ.",
                    keyboard=kb.get_json()
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

    async def is_waiting_confirm_data(message: Message) -> bool:
        if message.text and message.text.lower() in ["начать", "start", "/start"]:
            return False
        state_dict = await get_fsm_step(message.from_id)
        return state_dict is not None and state_dict.get("step") == "confirm_data"

    @bot.on.message(func=is_waiting_confirm_data)
    async def process_confirm_data(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            text = message.text.strip().lower()
            state_dict = await get_fsm_step(vk_id)

            import json

            if text == "верно":
                date_str = state_dict.get("date", "")
                city_str = state_dict.get("city", "")

                await set_user_state(vk_id, json.dumps({"step": "time", "date": date_str, "city": city_str}))
                kb = Keyboard(inline=True)
                kb.add(Text("Не знаю время (12:00)"), color=KeyboardButtonColor.SECONDARY)
                await message.answer("Укажите ВРЕМЯ рождения (например, 14:30):", keyboard=kb.get_json())
            elif text == "изменить":
                await set_user_state(vk_id, json.dumps({"step": "date"}))
                await message.answer("Укажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):")
            else:
                kb = Keyboard(inline=True)
                kb.add(Text("ВЕРНО"), color=KeyboardButtonColor.POSITIVE)
                kb.add(Text("ИЗМЕНИТЬ"), color=KeyboardButtonColor.NEGATIVE)
                await message.answer("Используйте кнопки 'ВЕРНО' или 'ИЗМЕНИТЬ'.", keyboard=kb.get_json())
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
                await asyncio.sleep(5)

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

                    # Split base_text if "БАЗА" exists
                    import re
                    parts = re.split(r"(?i)\bБАЗА\b", base_text, maxsplit=1)

                    if len(parts) > 1:
                        intro = parts[0].strip()
                        main_part = "БАЗА\n" + parts[1].strip()

                        await message.answer(intro)
                        await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")
                        await asyncio.sleep(4)

                        try:
                            await message.answer(main_part, keyboard=kb_json)
                        except Exception as e:
                            print(f"Error sending message with keyboard in process_time: {e}")
                            await message.answer(main_part)
                    else:
                        try:
                            await message.answer(base_text, keyboard=kb_json)
                        except Exception as e:
                            print(f"Error sending message with keyboard in process_time: {e}")
                            await message.answer(base_text)
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

    async def is_waiting_oracle_cut(message: Message) -> bool:
        if message.text and message.text.lower() in ["начать", "start", "/start", "лайн голос"]:
            return False
        state_dict = await get_fsm_step(message.from_id)
        return state_dict is not None and state_dict.get("step") == "oracle_cut"

    @bot.on.message(func=is_waiting_oracle_cut)
    async def process_oracle_cut(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            import json
            state_dict = await get_fsm_step(vk_id)
            question = state_dict.get("question", "")

            await set_user_state(vk_id, json.dumps({"step": "oracle_half", "question": question}))

            kb = Keyboard(inline=True)
            kb.add(Text("ВЕРХНЯЯ ЧАСТЬ"), color=KeyboardButtonColor.SECONDARY)
            kb.add(Text("НИЖНЯЯ ЧАСТЬ"), color=KeyboardButtonColor.SECONDARY)

            await message.answer(
                "Колода разделена надвое. Откуда будем тянуть карты?",
                keyboard=kb.get_json()
            )
        finally:
            active_tasks.discard(vk_id)

    async def is_waiting_oracle_half(message: Message) -> bool:
        if message.text and message.text.lower() in ["начать", "start", "/start", "лайн голос"]:
            return False
        state_dict = await get_fsm_step(message.from_id)
        return state_dict is not None and state_dict.get("step") == "oracle_half"

    @bot.on.message(func=is_waiting_oracle_half)
    async def process_oracle_half(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            import json
            text = message.text.strip().upper()
            state_dict = await get_fsm_step(vk_id)
            question = state_dict.get("question", "")

            import random
            if "ВЕРХНЯЯ" in text:
                pool = list(range(0, 39))
            else:
                pool = list(range(39, 78))

            random.shuffle(pool)

            # THE FIX: Slice the pool to 30 cards to respect VK's 6-row inline keyboard limit
            pool = pool[:10]

            await set_user_state(vk_id, json.dumps({
                "step": "oracle_draw",
                "question": question,
                "drawn_cards": [],
                "pool": pool
            }))

            from vkbottle import Callback
            kb = Keyboard(inline=True)
            for i, card_id in enumerate(pool):
                if i > 0 and i % 5 == 0:
                    kb.row()
                kb.add(Callback("🎴", payload={"oracle_card": card_id}))

            await message.answer(
                "Выбери ровно 3 карты из своей стопки:",
                keyboard=kb.get_json()
            )
        finally:
            active_tasks.discard(vk_id)

    async def process_oracle_final(vk_id: int, text: str, card_ids: list):
        user = await get_user(vk_id)
        if not user:
            return

        import datetime
        import asyncio
        from ai_service import generate_text

        try:
            attachments = []
            uploader = PhotoMessageUploader(bot.api)
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for cid in card_ids:
                    url = f"https://raw.githubusercontent.com/peexthree/VKbot/main/cards/{cid}.jpeg"
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                photo = await uploader.upload(data)
                                attachments.append(photo)
                            else:
                                print(f"Failed to fetch {url}: {resp.status}")
                    except Exception as e:
                        print(f"Failed to upload oracle tarot card {cid}: {e}")

            # Send cards with delays
            messages = ["ПЕРВАЯ КАРТА...", "ВТОРАЯ КАРТА...", "ТРЕТЬЯ КАРТА..."]
            delays = [1, 1, 2]

            for i in range(3):
                if i < len(attachments):
                    await bot.api.messages.send(
                        peer_id=vk_id,
                        message=messages[i],
                        attachment=attachments[i],
                        random_id=0
                    )
                else:
                    await bot.api.messages.send(
                        peer_id=vk_id,
                        message=messages[i],
                        random_id=0
                    )
                await asyncio.sleep(delays[i])

            await bot.api.messages.send(
                peer_id=vk_id,
                message="АНАЛИЗИРУЮ СИНХРОНИЗАЦИЮ...",
                random_id=0
            )
            await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
            await asyncio.sleep(4)

            # Build prompt with user context
            purchased = user.get("purchased_sections", {})
            sex_val = purchased.get("sex_val", 0)
            gender_str = "ЖЕНЩИНА" if sex_val == 1 else "МУЖЧИНА"

            prompt = (
                f"КОНТЕКСТ: {gender_str}. "
                f"Пользователь задает вопрос: {text}. "
                f"Выпали карты: {card_ids[0]}, {card_ids[1]}, {card_ids[2]}. "
                "Сделай дерзкий, интересный ответ-синтез по этим картам. Сами карты в тексте не называй, просто дай суть основанную по гаданиям таро."
            )

            result_text = await generate_text(prompt)
            if not result_text:
                result_text = "Оракул молчит. Попробуй позже."

            # Update database
            purchased["last_oracle_time"] = datetime.datetime.now().isoformat()
            if purchased.get("oracle_access", False):
                purchased["oracle_access"] = False # consume the pass

            await update_user(vk_id, {"purchased_sections": purchased})

            kb_json = await get_sections_keyboard(vk_id, user)

            await bot.api.messages.send(
                peer_id=vk_id,
                message=result_text,
                keyboard=kb_json,
                random_id=0
            )

        except Exception as e:
            print(f"Error in process_oracle_final: {e}")

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
            await asyncio.sleep(5)

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

                kb_json = await get_sections_keyboard(vk_id, user)

                import re
                parts = re.split(r"(?i)\bБАЗА\b", base_text, maxsplit=1)

                if len(parts) > 1:
                    intro = parts[0].strip()
                    main_part = "✦ БАЗА ✦\n\n" + parts[1].strip()

                    await message.answer(intro)
                    await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")
                    await asyncio.sleep(4)

                    try:
                        await message.answer(main_part, keyboard=kb_json)
                    except Exception as e:
                        print(f"Error sending message with keyboard in process_city: {e}")
                        await message.answer(main_part)
                else:
                    full_text = f"✦ БАЗА ✦\n\n{base_text}"
                    try:
                        await message.answer(full_text, keyboard=kb_json)
                    except Exception as e:
                        print(f"Error sending message with keyboard in process_city: {e}")
                        await message.answer(full_text)
            else:
                base_text = "ДАННЫЕ СОХРАНЕНЫ. СИСТЕМА В ОЖИДАНИИ."
                kb_json = await get_sections_keyboard(vk_id, user)
                try:
                    await message.answer(f"✦ БАЗА ✦\n\n{base_text}", keyboard=kb_json)
                except Exception as e:
                    await message.answer(f"✦ БАЗА ✦\n\n{base_text}")

            # Отправляем навигатор отдельно
            try:
                await message.answer("Используйте меню для навигации:", keyboard=get_dynamic_keyboard(user))
            except Exception as e:
                print(f"Error sending navigation menu in process_city: {e}")

        finally:
            active_tasks.discard(vk_id)


    @bot.on.message(text=["✦ Главное меню", "Главное меню", "В ГЛАВНОЕ МЕНЮ", "МЕНЮ", "НАЗАД"])
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

    @bot.on.message(text=["✦ Баланс", "Баланс"])
    async def show_balance(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if not user:
            await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
            return

        purchased = user.get("purchased_sections", {})

        # Calculate purchased value roughly
        value = 0
        if purchased.get("sex"): value += 100
        if purchased.get("money"): value += 90
        if purchased.get("shadow"): value += 70
        if purchased.get("final"): value += 120

        await message.answer(f"ТВОЙ БАЛАНС.\nПриобретено услуг на сумму: {value} RUB.")

    async def get_storefront_keyboard(purchased: dict) -> str | None:
        import json
        buttons = []

        if not purchased.get("sex"):
            buttons.append([{"action": {"type": "text", "label": "СЕКС"}, "color": "secondary"}])

        if not purchased.get("money"):
            buttons.append([{"action": {"type": "text", "label": "ДЕНЬГИ"}, "color": "secondary"}])

        if not purchased.get("shadow"):
            buttons.append([{"action": {"type": "text", "label": "ТЕНЬ"}, "color": "secondary"}])

        if not purchased.get("final"):
            buttons.append([{"action": {"type": "text", "label": "ФИНАЛ"}, "color": "secondary"}])

        purchased_count = sum([bool(purchased.get("sex")), bool(purchased.get("money")), bool(purchased.get("shadow")), bool(purchased.get("final"))])
        if purchased_count < 2:
            buttons.append([{"action": {"type": "text", "label": "БАНДЛ"}, "color": "secondary"}])

        # Oracle freemium skip button (always added as an option to purchase)
        buttons.append([{"action": {"type": "text", "label": "ВОПРОС СУДЬБЕ"}, "color": "secondary"}])

        if buttons:
            keyboard_obj = {
                "inline": True,
                "buttons": buttons
            }
            return json.dumps(keyboard_obj, ensure_ascii=False)
        return None

    @bot.on.message(text=["✦ Услуги", "Услуги"])
    async def show_services(message: Message):
        vk_id = message.from_id
        user = await get_user(vk_id)
        if not user:
            await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
            return

        purchased = user.get("purchased_sections", {})
        storefront_kb = await get_storefront_keyboard(purchased)

        if storefront_kb:
            await message.answer("ВЫБЕРИТЕ УСЛУГУ:", keyboard=storefront_kb)
        else:
            kb_json = await get_sections_keyboard(vk_id, user)
            await message.answer("ВСЕ РАЗДЕЛЫ ОТКРЫТЫ. НОВЫХ УСЛУГ ПОКА НЕТ.", keyboard=kb_json)

    @bot.on.message(text=["✦ Мой профиль", "Мой профиль"])
    async def show_profile(message: Message):
        import json
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

        storefront_kb = await get_storefront_keyboard(purchased)
        status_text = "" if storefront_kb else "\n\nВСЕ РАЗДЕЛЫ ОТКРЫТЫ."

        profile_text = (
            f"✦ ПРОФИЛЬ АСКЕТА ✦\n\n"
            f"{name_line}ТОЧКА ВХОДА: {date} {time}\n"
            f"ЛОКАЦИЯ: {city}"
            f"{status_text}"
        )

        kb_json = await get_sections_keyboard(vk_id, user)
        await message.answer(profile_text, keyboard=kb_json)


    @bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=dict)
    async def message_event_handler(event: dict):
        obj = event.get("object", {})
        vk_id = obj.get("user_id")
        peer_id = obj.get("peer_id")
        event_id = obj.get("event_id")
        payload = obj.get("payload", {})

        if not vk_id or not payload or "oracle_card" not in payload:
            return

        card_id = payload["oracle_card"]

        try:
            import json
            # Stop loading animation
            await bot.api.messages.send_message_event_answer(
                event_id=event_id,
                user_id=vk_id,
                peer_id=peer_id
            )

            state_dict = await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "oracle_draw":
                return

            drawn_cards = state_dict.get("drawn_cards", [])
            pool = state_dict.get("pool", [])

            if card_id not in drawn_cards:
                drawn_cards.append(card_id)

            if len(drawn_cards) < 3:
                state_dict["drawn_cards"] = drawn_cards
                await set_user_state(vk_id, json.dumps(state_dict))

                from vkbottle import Callback
                kb = Keyboard(inline=True)

                # Render only available cards
                btn_count = 0
                for c_id in pool:
                    if c_id not in drawn_cards:
                        if btn_count > 0 and btn_count % 5 == 0:
                            kb.row()
                        kb.add(Callback("🎴", payload={"oracle_card": c_id}))
                        btn_count += 1

                await bot.api.messages.edit(
                    peer_id=peer_id,
                    message=f"Выбрано: {len(drawn_cards)}/3...",
                    conversation_message_id=obj.get("conversation_message_id"),
                    keyboard=kb.get_json()
                )
            else:
                # 3 cards selected
                await set_user_state(vk_id, "") # Clear FSM state

                # To completely remove the keyboard, we need to pass an empty keyboard payload
                empty_kb = Keyboard(inline=True)

                await bot.api.messages.edit(
                    peer_id=peer_id,
                    message="Выбрано: 3/3. Карты собраны.",
                    conversation_message_id=obj.get("conversation_message_id"),
                    keyboard=empty_kb.get_json()
                )

                # Trigger process_oracle_final asynchronously to avoid blocking callback
                import asyncio
                asyncio.create_task(process_oracle_final(vk_id, state_dict["question"], drawn_cards))

        except Exception as e:
            print(f"Error in message_event_handler: {e}")

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
            elif amount_val == 50:
                section = "oracle"

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
            elif section == "oracle":
                purchased["oracle_access"] = True
                await update_user(vk_id, {"purchased_sections": purchased})
                await bot.api.messages.send(peer_id=vk_id, message="ОПЛАТА УСПЕШНА.\n\nНАПИШИ СВОЙ ВОПРОС СУДЬБЕ ПРЯМО СЕЙЧАС.", random_id=0)
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

            if section != "oracle":
                await bot.api.messages.send(
                    peer_id=vk_id,
                    message="Используйте меню для вызова нужного раздела:",
                    keyboard=kb_json,
                    random_id=0
                )

        finally:
            active_tasks.discard(vk_id)

    @bot.on.message(text=["ЛАЙН ГОЛОС"])
    async def god_mode_handler(message: Message):
        vk_id = message.from_id

        if vk_id in active_tasks:
            return

        active_tasks.add(vk_id)
        try:
            user = await get_user(vk_id)
            if not user:
                await message.answer("Сначала напиши 'Начать'")
                return

            purchased = user.get("purchased_sections", {})
            purchased["sex"] = True
            purchased["money"] = True
            purchased["shadow"] = True
            purchased["final"] = True

            await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})

            # Need to get updated user for keyboard
            user = await get_user(vk_id)
            kb_json = await get_sections_keyboard(vk_id, user)

            await message.answer(
                "ЛАЙН ПОДАЛ ГОЛОС. СИСТЕМА УЗНАЛА СВОЕГО СОЗДАТЕЛЯ. ВСЕ ОГРАНИЧЕНИЯ СНЯТЫ. ПРИЯТНОГО АНАЛИЗА, МОЙ ПОВЕЛИТЕЛЬ ИГОРЬ.",
                keyboard=kb_json
            )
        finally:
            active_tasks.discard(vk_id)

    @bot.on.message(text=["СЕКС", "ДЕНЬГИ", "ТЕНЬ", "ФИНАЛ", "БАНДЛ", "ВОПРОС СУДЬБЕ"])
    async def handle_storefront_purchase(message: Message):
        import json
        text = message.text.upper()

        service_map = {
            "СЕКС": {"text": "ГРЯЗНЫЕ СЕКРЕТЫ\nСЕКС - 100 РУБ", "photo": "sex.jpeg", "amount": 100},
            "ДЕНЬГИ": {"text": "МАГНИТ ДЛЯ КРИПТЫ\nДЕНЬГИ - 90 РУБ", "photo": "money.jpeg", "amount": 90},
            "ТЕНЬ": {"text": "ТЕМНЫЕ ДЕМОНЫ\nТЕНЬ - 70 РУБ", "photo": "demon1.jpg", "amount": 70},
            "ФИНАЛ": {"text": "ПОЛНЫЙ РАСКЛАД\nФИНАЛ - 120 РУБ", "photo": "full.jpeg", "amount": 120},
            "БАНДЛ": {"text": "ВЕСЬ ПАКЕТ СУДЬБЫ\nБАНДЛ - 300 РУБ", "photo": "full1.jpg", "amount": 300},
            "ВОПРОС СУДЬБЕ": {"text": "ПРОПУСК ТАЙМЕРА\nВОПРОС СУДЬБЕ - 50 РУБ", "photo": "ora.jpeg", "amount": 50}
        }

        service_info = service_map.get(text)
        if not service_info:
            return

        photo_id = await get_cover_photo_id(service_info["photo"])

        keyboard_obj = {
            "inline": True,
            "buttons": [[{
                "action": {"type": "vkpay", "hash": f"action=pay-to-group&group_id=219181948&amount={service_info['amount']}"}
            }]]
        }
        kb_json = json.dumps(keyboard_obj, ensure_ascii=False)

        if photo_id:
            await message.answer(service_info["text"], attachment=photo_id, keyboard=kb_json)
        else:
            await message.answer(service_info["text"], keyboard=kb_json)

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
            await asyncio.sleep(5)

            date = user.get("birth_date", "неизвестно")
            time = user.get("birth_time", "неизвестно")
            city = user.get("birth_city", "неизвестно")
            first_name = purchased.get("first_name", "")

            from ai_service import generate_section
            core_profile = user.get("core_profile", "")
            sex_val = purchased.get("sex_val", 0)

            result_text = await generate_section(target_section, date, time, city, core_profile, first_name, sex_val)

            if not result_text:
                kb_json = await get_sections_keyboard(vk_id, user)
                await message.answer("Ошибка генерации.", keyboard=kb_json)
                return

            if first_name:
                result_text = f"{first_name},\n\n" + result_text

            if target_section in ["sex", "money", "shadow", "final"]:
                import re
                import random
                match = re.search(r"ID_?ТАРО:\s*(\d+)", result_text)
                if match:
                    num = int(match.group(1))
                    if 0 <= num <= 77:
                        card_id = str(num)
                    else:
                        card_id = str(random.randint(0, 77))
                else:
                    card_id = str(random.randint(0, 77))

                print(f"[DEBUG] Parsed Card ID: {card_id}")

                photo_attachment = None
                try:
                    uploader = PhotoMessageUploader(bot.api)
                    import aiohttp
                    url = f"https://raw.githubusercontent.com/peexthree/VKbot/main/cards/{card_id}.jpeg"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                photo_attachment = await uploader.upload(data)
                            else:
                                print(f"Failed to fetch {url}: {resp.status}")
                except Exception as e:
                    print(f"Failed to upload tarot card {card_id}: {e}")

                # Убираем техническую строку с ID_ТАРО из финального текста
                display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", result_text).strip()

                # Split display_text if the section header exists (e.g. "СЕКС", "ДЕНЬГИ", "ТЕНЬ", "ФИНАЛ")
                section_header = target_section_ru = {
                    "sex": "СЕКС",
                    "money": "ДЕНЬГИ",
                    "shadow": "ТЕНЬ",
                    "final": "ФИНАЛ"
                }[target_section]

                parts = re.split(rf"(?i)\b{section_header}\b", display_text, maxsplit=1)

                intro = ""
                main_part = display_text

                if len(parts) > 1:
                    intro = parts[0].strip()
                    main_part = f"{section_header}\n" + parts[1].strip()

                kb_json = await get_sections_keyboard(vk_id, user)

                if intro:
                    if photo_attachment:
                        await message.answer(intro, attachment=photo_attachment)
                    else:
                        await message.answer(intro)

                    await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")
                    await asyncio.sleep(4)

                    try:
                        await message.answer(main_part, keyboard=kb_json)
                    except Exception as e:
                        print(f"Error sending message with keyboard: {e}")
                        await message.answer(main_part)
                else:
                    try:
                        if photo_attachment:
                            await message.answer(display_text, attachment=photo_attachment, keyboard=kb_json)
                        else:
                            await message.answer(display_text, keyboard=kb_json)
                    except Exception as inner_e:
                        print(f"Error sending message with attachment and keyboard: {inner_e}")
                        if photo_attachment:
                            await message.answer(display_text, attachment=photo_attachment)
                        else:
                            await message.answer(display_text)

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

    @bot.on.message()
    async def oracle_handler(message: Message):
        vk_id = message.from_id
        if vk_id in active_tasks:
            return

        user = await get_user(vk_id)
        if not user:
            return

        # Игнорируем команды и системные сообщения
        text = message.text.strip()
        if not text or text.lower() in ["начать", "start", "/start", "лайн голос"] or text.startswith("✦"):
            return

        # Проверяем, не в FSM ли мы
        state_dict = await get_fsm_step(vk_id)
        if state_dict is not None and "step" in state_dict:
            return

        active_tasks.add(vk_id)
        try:
            import datetime
            import json

            purchased = user.get("purchased_sections", {})
            last_oracle_time_str = purchased.get("last_oracle_time")
            has_paid_access = purchased.get("oracle_access", False)

            allow_access = False
            if has_paid_access:
                allow_access = True
            else:
                if not last_oracle_time_str:
                    allow_access = True
                else:
                    try:
                        last_time = datetime.datetime.fromisoformat(last_oracle_time_str)
                        if (datetime.datetime.now() - last_time).total_seconds() >= 24 * 3600:
                            allow_access = True
                    except ValueError:
                        allow_access = True

            if not allow_access:
                last_time = datetime.datetime.fromisoformat(last_oracle_time_str)
                remaining = datetime.timedelta(hours=24) - (datetime.datetime.now() - last_time)
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)

                # Payment keyboard for Oracle
                keyboard_obj = {
                    "inline": True,
                    "buttons": [[{
                        "action": {"type": "vkpay", "hash": "action=pay-to-group&group_id=219181948&amount=50"}
                    }]]
                }
                kb_json = json.dumps(keyboard_obj, ensure_ascii=False)

                await message.answer(
                    f"СЕАНС НЕДОСТУПЕН. ВРЕМЯ ДО ВОССТАНОВЛЕНИЯ: {hours:02d}:{minutes:02d}\nВОПРОС СУДЬБЕ - 50 РУБ",
                    keyboard=kb_json
                )
                return

            # Start Oracle FSM
            await set_user_state(vk_id, json.dumps({"step": "oracle_cut", "question": text}))

            kb = Keyboard(inline=True)
            kb.add(Text("СДВИНУТЬ КОЛОДУ"), color=KeyboardButtonColor.PRIMARY)

            await message.answer(
                "Вопрос принят. Энергия сформирована. Сдвинь колоду, чтобы задать вектор.",
                keyboard=kb.get_json()
            )

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
