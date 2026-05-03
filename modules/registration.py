import asyncio
import json
import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, generate_pdf, get_fsm_step,  upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, active_tasks, cover_cache

labeler = BotLabeler()

@labeler.message(text=["СБРОС"])
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

@labeler.message(text=["Начать", "start", "/start"])
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
        psycho_positioning = "Интеллектуальный анализ подсознания через систему символов. Этот инструмент создан для тех, кто готов заглянуть за грань привычного и получить жесткие, структурированные ответы."
        if bdate and city:
            await set_user_state(vk_id, json.dumps({"step": "confirm_data", "date": bdate, "city": city}))
            kb = Keyboard(inline=True)
            kb.add(Text("ВЕРНО"), color=KeyboardButtonColor.POSITIVE)
            kb.add(Text("ИЗМЕНИТЬ"), color=KeyboardButtonColor.NEGATIVE)
            await message.answer(
                f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nПривет, {first_name}.\n{psycho_positioning}\n\n"
                f"ТВОЙ ГОРОД - {city}, ДАТА РОЖДЕНИЯ - {bdate}. ЭТИ ДАННЫЕ ВЕРНЫ? СИСТЕМА НЕ ПРОЩАЕТ ОШИБОК ПРИ РАСЧЕТЕ СУДЬБЫ.",
                keyboard=kb.get_json()
            )
        elif bdate:
            await set_user_state(vk_id, json.dumps({"step": "time", "date": bdate}))
            kb = Keyboard(inline=True)
            kb.add(Text("Не знаю время (12:00)"), color=KeyboardButtonColor.SECONDARY)
            await message.answer(
                f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nПривет, {first_name}.\n{psycho_positioning}\n\nТвоя дата рождения ({bdate}) загружена.\n"
                "Укажите ВРЕМЯ рождения (например, 14:30):", keyboard=kb.get_json()
            )
        elif city:
            await set_user_state(vk_id, json.dumps({"step": "date", "city": city}))
            await message.answer(
                f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\nПривет, {first_name}.\n{psycho_positioning}\n\nТвой город ({city}) загружен.\n"
                "Укажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):"
            )
        else:
            await set_user_state(vk_id, json.dumps({"step": "date"}))
            greeting = f"Привет, {first_name}." if first_name else "Привет."
            await message.answer(
                f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\n{greeting}\n{psycho_positioning}\n\n"
                "Укажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):"
            )
    finally:
        active_tasks.discard(vk_id)

async def is_waiting_confirm_data(message: Message) -> bool:
    if message.text and message.text.lower() in ["начать", "start", "/start"]:
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "confirm_data"

@labeler.message(func=is_waiting_confirm_data)
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

async def is_waiting_date(message: Message) -> bool:
    if message.text and message.text.lower() in ["начать", "start", "/start"]:
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "date"

@labeler.message(func=is_waiting_date)
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

@labeler.message(func=is_waiting_time)
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
            active_skin = user.get("active_skin", "olesya") if user else "olesya"
            base_text = await generate_section("base", date_str, time_str, city_str_existing, skin=active_skin)

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

@labeler.message(func=is_waiting_city)
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
        active_skin = user.get("active_skin", "olesya") if user else "olesya"
        base_text = await generate_section("base", date, time, city, core_profile, skin=active_skin)

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

@labeler.message(text=["✦ Главное меню", "Главное меню", "В ГЛАВНОЕ МЕНЮ", "МЕНЮ", "НАЗАД"])
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
