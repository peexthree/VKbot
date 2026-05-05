from cache import acquire_lock, release_lock
from modules.states import MyStates
import asyncio
import json
import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader, Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, get_fsm_step, upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, cover_cache

labeler = BotLabeler()

@labeler.message(text=["СБРОС"])
async def reset_user_handler(message: Message):
    vk_id = message.from_id

    await update_user(vk_id, {
        "birth_date": "",
        "birth_time": "",
        "birth_city": "",
        "purchased_sections": {},
        "core_profile": ""
    })

    await set_user_state(vk_id, "")

    await message.answer("СИСТЕМА ОБНУЛЕНА. ТЫ ДЛЯ МЕНЯ ТЕПЕРЬ НИКТО. Напиши 'Начать' для теста с нуля.")

@labeler.message(text=["Начать", "start", "/start"])
async def start_handler(message: Message):
    vk_id = message.from_id
    from database import set_user_state
    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        user = await get_user(vk_id)

        if user and user.get("birth_date") and user.get("birth_time") and user.get("birth_city"):
            purchased = user.get("purchased_sections", {})
            first_name = purchased.get("first_name", "")
            greeting = f"С возвращением, {first_name}." if first_name else "С возвращением."
            await message.answer(f"СИСТЕМА АНАЛИЗА СУДЬБЫ АКТИВИРОВАНА.\n\n{greeting}", keyboard=get_dynamic_keyboard(user))
            return

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
            logger.error(f"Ошибка: {str(e)}")

        if not user:
            user = await create_user(vk_id, "", "", "")

        if user:
            purchased = user.get("purchased_sections", {})
            purchased["first_name"] = first_name
            purchased["sex_val"] = sex 
            await update_user(vk_id, {"purchased_sections": purchased})

        import json
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
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_CONFIRM_DATA)
async def process_confirm_data(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

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
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_FOR_DATE)
async def process_date(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        date_str = message.text.strip()

        import json
        await set_user_state(vk_id, json.dumps({"step": "time", "date": date_str}))

        kb = Keyboard(inline=True)
        kb.add(Text("Не знаю время (12:00)"), color=KeyboardButtonColor.SECONDARY)
        await message.answer("Укажите ВРЕМЯ рождения (например, 14:30):", keyboard=kb.get_json())
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_FOR_TIME)
async def process_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        time_str = message.text.strip()
        if time_str.lower() == "не знаю время" or time_str.lower() == "не знаю время (12:00)":
            time_str = "12:00"

        state_dict = await get_fsm_step(vk_id)
        date_str = state_dict.get("date", "")
        city_str_existing = state_dict.get("city", "")

        import json

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

            await message.answer("ЧИТАЮ ЛИНИИ ВЕРОЯТНОСТИ...")
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

            base_text = await generate_section("base", date_str, time_str, city_str_existing, skin=active_skin)

            if base_text:
                if first_name:
                    base_text = f"{first_name},\n\n" + base_text

                kb_json = await get_sections_keyboard(vk_id, user)

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
                        logger.error(f"Ошибка: {str(e)}")
                        await message.answer(main_part)
                else:
                    try:
                        await message.answer(base_text, keyboard=kb_json)
                    except Exception as e:
                        logger.error(f"Ошибка: {str(e)}")
                        await message.answer(base_text)
            else:
                try:
                    await message.answer("Используйте меню для навигации:", keyboard=get_dynamic_keyboard(user))
                except Exception as e:
                    logger.error(f"Ошибка: {str(e)}")
        else:
            await set_user_state(vk_id, json.dumps({"step": "city", "date": date_str, "time": time_str}))
            await message.answer("Укажите ГОРОД рождения:")
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_FOR_CITY)
async def process_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        city_str = message.text.strip()
        state_dict = await get_fsm_step(vk_id)

        date = state_dict.get("date", "")
        time = state_dict.get("time", "")
        city = city_str

        user = await update_user(vk_id, {
            "birth_date": date,
            "birth_time": time,
            "birth_city": city,
            "balance": 700,
            "welcome_bonus_received": True
        })
        if not user:
            await message.answer("СИСТЕМА ДАЛА СБОЙ. Не удалось сохранить данные в базу. Повторите попытку позже.")
            return

        await set_user_state(vk_id, "")

        import json
        from modules.utils import get_dynamic_keyboard

        kb_inline = {
            "inline": True,
            "buttons": [[{
                "action": {
                    "type": "callback",
                    "payload": json.dumps({"cmd": "global_cut", "target": "welcome"}),
                    "label": "СДЕЛАТЬ ПЕРВЫЙ РАЗБОР"
                },
                "color": "primary"
            }]]
        }

        try:
            # Отправляем оба сообщения мгновенно
            await message.answer(
                "Я закончила изучение твоей точки входа в этот мир. Теперь система знает о тебе больше, чем ты сам.\n\n"
                "В качестве дара за доверие я зачислила на твой счет 700 Энергии звезд. Используй нижнее меню для навигации.",
                keyboard=get_dynamic_keyboard(user)
            )

            await message.answer(
                "Твоя матрица готова к чтению. Ты можешь изучить разделы меню, либо позволить мне сделать первый базовый разбор прямо сейчас.",
                keyboard=json.dumps(kb_inline, ensure_ascii=False)
            )
        except Exception as e:
            logger.error(f"Ошибка: {str(e)}")
            await message.answer("Твоя матрица готова к чтению. Ты можешь изучить разделы меню, либо позволить мне сделать первый базовый разбор прямо сейчас.", keyboard=json.dumps(kb_inline, ensure_ascii=False))

    finally:
        await release_lock(vk_id)

@labeler.message(text=["✦ Главное меню", "Главное меню", "В ГЛАВНОЕ МЕНЮ", "МЕНЮ", "НАЗАД", "✦ ГЛАВНОЕ МЕНЮ 🏠"])
async def back_to_main_menu(message: Message):
    vk_id = message.from_id
    from database import set_user_state
    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
        await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
        return

    try:
        kb_json = await get_sections_keyboard(vk_id, user)
        try:
            await message.answer(
                "ТВОИ ДАННЫЕ В СИСТЕМЕ. КУДА ДВИНЕМСЯ ДАЛЬШЕ?",
                keyboard=kb_json
            )
        except Exception as e:
            await message.answer(
                "ТВОИ ДАННЫЕ В СИСТЕМЕ. КУДА ДВИНЕМСЯ ДАЛЬШЕ?"
            )
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
    finally:
        await release_lock(vk_id)
