from modules.bot_init import bot
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
from modules.utils import get_fsm_step, upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, cover_cache

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

        await set_user_state(vk_id, "waiting_for_onboarding_data")
        await message.answer(
            "✦ СИСТЕМА АНТИ-ТАР АКТИВИРОВАНА ✦ 😈\n\n"
            "Забудь о ванильных гороскопах. Здесь тебя ждет жесткий разбор без прикрас.\n"
            "Для калибровки профиля и начисления 700 Энергии звезд напиши свою дату, время и город рождения одним текстом (например: 15 мая 1990, 14:30, Казань)."
        )
    finally:
        await release_lock(vk_id)


@labeler.message(state=MyStates.WAITING_FOR_ONBOARDING_DATA)
async def process_onboarding_data(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        user_text = message.text.strip()
        await message.answer("Анализирую ваши данные... 👁‍🗨")
        await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

        prompt = (
            "Извлеки из текста дату рождения, время рождения и город. "
            "Ответь строго в формате JSON: {\"date\": \"ДД.ММ.ГГГГ\", \"time\": \"ЧЧ:ММ\", \"city\": \"Город\"}. "
            f"Текст пользователя: {user_text}"
        )

        response = await generate_text("Ты - парсер данных. Выдавай только валидный JSON.\n" + prompt)

        try:
            if not response:
                raise ValueError("Empty response from AI")
            cleaned_response = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned_response)
            date = data.get("date", "01.01.1990")
            time = data.get("time", "12:00")
            city = data.get("city", "Москва")
        except (json.JSONDecodeError, ValueError, Exception):
            date = "01.01.1990"
            time = "12:00"
            city = "Москва"

        insight_prompt = f"Пользователь родился {date} в {time} в городе {city}. Напиши 2 жестких, дерзких и мистических предложения (инсайт) про его матрицу судьбы или влияние планет. Без приветствий, сразу к делу."
        insight = await generate_text("Ты - темный таролог.\n" + insight_prompt)

        user = await update_user(vk_id, {
            "birth_date": date,
            "birth_time": time,
            "birth_city": city,
            "balance": 700,
            "welcome_bonus_received": True
        })

        await set_user_state(vk_id, "")

        await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

        from modules.utils import get_dynamic_keyboard

        await message.answer(
            f"ДАННЫЕ ПРИНЯТЫ 🪐\nТебе начислено 700 Энергии звезд.\nТвоя базовая матрица загружена: {insight}",
            keyboard=get_dynamic_keyboard(user)
        )

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
