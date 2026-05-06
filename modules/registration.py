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
from ai_service import generate_text, generate_section, extract_birth_data
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

async def fetch_user_vk_data(vk_id: int):
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
        from loguru import logger
        logger.error(f"Ошибка: {str(e)}")
    return first_name, sex, bdate, city

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

        first_name, sex, bdate, city = await fetch_user_vk_data(vk_id)

        if not user:
            user = await create_user(vk_id, "", "", "")

        if user:
            purchased = user.get("purchased_sections", {})
            purchased["first_name"] = first_name
            purchased["sex_val"] = sex 
            await update_user(vk_id, {"purchased_sections": purchased})

        # Устанавливаем стейт и отправляем анти-тар приветствие
        await set_user_state(vk_id, "waiting_for_onboarding_data")
        await bot.state_dispenser.set(vk_id, MyStates.WAITING_FOR_ONBOARDING_DATA)
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
        await message.answer("Анализирую ваши координаты... 👁‍🗨")
        await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

        data = await extract_birth_data(user_text)

        if not data or not data.get("date") or not data.get("city"):
            await message.answer("Не удалось считать координаты. Напиши, пожалуйста, в формате: ДД.ММ.ГГГГ, Время, Город")
            return

        date = data.get("date")
        time = data.get("time", "12:00")
        city = data.get("city")

        # Сохраняем временные данные в стейт и переводим в состояние подтверждения
        state_payload = {
            "step": "confirm_data",
            "date": date,
            "time": time,
            "city": city
        }
        await set_user_state(vk_id, json.dumps(state_payload))

        # Устанавливаем стейт явно для FSM маршрутизации, если set_user_state не сделал этого для данного шага
        await bot.state_dispenser.set(vk_id, MyStates.WAITING_CONFIRM_DATA, raw_json=json.dumps(state_payload))

        kb = Keyboard(inline=True)
        kb.add(Callback("✅ ДАННЫЕ ВЕРНЫ", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("🔄 ОШИБКА. ИСПРАВИТЬ", payload={"cmd": "retry_registration"}), color=KeyboardButtonColor.SECONDARY)

        verification_text = (
            f"🪐 Данные рождения распознаны:\n"
            f"Дата: {date}\n"
            f"Время: {time}\n"
            f"Город: {city}\n\n"
            f"Проверь точность. Алгоритм не прощает ошибок во времени и месте."
        )

        await message.answer(verification_text, keyboard=kb.get_json())

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

async def parse_time(user_text: str) -> str | None:
    import re
    from ai_service import generate_text
    match = re.search(r"(\d{1,2})[\.:\-](\d{2})", user_text)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"

    if re.search(r"(?i)не\s*знаю|без|хз|нет", user_text):
        return "12:00"

    prompt = (
        f"Пользователь ответил: '{user_text}'. "
        f"Определи время рождения. "
        f"Верни строго в формате ЧЧ:ММ (например: 14:30). "
        f"Если время определить невозможно, верни 'None'."
    )
    res = await generate_text(prompt)

    if res and "None" not in res:
        m = re.search(r"(\d{1,2}:\d{2})", res)
        if m: return m.group(1)

    return None

async def finalize_city_and_register(vk_id: int, date_str: str, time_str: str, city_str: str) -> tuple:
    from database import get_user, create_user, update_user
    from ai_service import generate_text
    user = await get_user(vk_id)
    if not user:
        user = await create_user(vk_id, date_str, time_str, city_str)
    else:
        updates = {"birth_date": date_str, "birth_time": time_str, "birth_city": city_str}
        if not user.get("welcome_bonus_received"):
            updates["balance"] = user.get("balance", 0) + 700
            updates["welcome_bonus_received"] = True
        user = await update_user(vk_id, updates)

    insight_prompt = f"Пользователь родился {date_str} в {time_str} в городе {city_str}. Напиши 2 жестких, дерзких и мистических предложения (инсайт) про его матрицу судьбы или влияние планет. Без приветствий, сразу к делу."
    insight = await generate_text("Ты - темный таролог.\n" + insight_prompt)
    return user, insight

@labeler.message(state=MyStates.WAITING_FOR_TIME)
async def process_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        user_text = message.text.strip()
        state_dict = await get_fsm_step(vk_id)

        if not state_dict or state_dict.get("step") != "time":
            await set_user_state(vk_id, "")
            return

        date_str = state_dict.get("date", "")
        await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

        time_str = await parse_time(user_text)

        if time_str:
            state_dict["step"] = "city"
            state_dict["time"] = time_str
            await set_user_state(vk_id, json.dumps(state_dict))
            await message.answer("Укажите ГОРОД вашего рождения (например: Москва):")
        else:
            await message.answer("Формат времени не распознан. Пожалуйста, напишите в формате ЧЧ:ММ (например: 14:30), либо напишите 'не знаю'.")

    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_FOR_CITY)
async def process_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        user_text = message.text.strip().title()
        state_dict = await get_fsm_step(vk_id)

        if not state_dict or state_dict.get("step") != "city":
            await set_user_state(vk_id, "")
            return

        date_str = state_dict.get("date", "")
        time_str = state_dict.get("time", "")
        city_str = user_text

        await set_user_state(vk_id, "")
        await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")

        user, insight = await finalize_city_and_register(vk_id, date_str, time_str, city_str)

        from modules.utils import get_dynamic_keyboard
        await message.answer(
            f"ДАННЫЕ ПРИНЯТЫ 🪐\nТебе начислено 700 Энергии звезд.\nТвоя базовая матрица загружена: {insight}",
            keyboard=get_dynamic_keyboard(user)
        )

    finally:
        await release_lock(vk_id)
