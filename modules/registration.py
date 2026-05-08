from loguru import logger
from modules.bot_init import bot
from cache import acquire_lock, release_lock
import json
from vkbottle.bot import BotLabeler, Message
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from database import get_user, update_user, set_user_state, get_user_state, create_user, delete_user
from ai_service import extract_birth_data
from modules.utils import get_sections_keyboard

labeler = BotLabeler()

@labeler.message(text=["СБРОС"])
async def reset_user_handler(message: Message):
    vk_id = message.from_id

    await delete_user(vk_id)

    await set_user_state(vk_id, "")

    await message.answer("СИСТЕМА ОБНУЛЕНА.  Напиши 'Начать' для теста с нуля.")

@labeler.message(text=["Начать", "start", "/start"])
async def start_handler(message: Message):
    vk_id = message.from_id

    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        user = await get_user(vk_id)
        if not user: return

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

        # Ensure we have fallback values if API returns None or empty
        if not bdate:
            bdate = "Не указана"
        if not city:
            city = "Не указан"

        await set_user_state(vk_id, json.dumps({
            "step": "confirm_data",
            "date": bdate,
            "time": "12:00",
            "city": city
        }))

        kb = Keyboard(inline=True)
        kb.add(Callback("✅ ВЕРНО", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("🔄 ИЗМЕНИТЬ", payload={"cmd": "edit_onboarding_data"}), color=KeyboardButtonColor.NEGATIVE)

        await message.answer(
            f"✦ ДОБРО ПОЖАЛОВАТЬ В ЦИФРОВОЙ ГРИМУАР, {first_name.upper() if first_name else 'ИСКАТЕЛЬ'} ✦ 🔮\n\n"
            "Я АНТИ-ТАР - твой проводник в мир глубокого самопознания. Здесь нет ванильных гороскопов - только жесткий, честный разбор твоей матрицы судьбы.\n\n"
            "Мы вскроем твои теневые стороны, финансовый потенциал и скрытую энергию. Никакой воды, только факты, которые изменят твое восприятие себя.\n\n"
            "Для инициализации профиля и получения приветственного дара в 700 Энергии звезд я считал твои данные из профиля:\n"
            f"Дата рождения: {bdate}\n"
            f"Город рождения: {city}\n\n"
            "Эти данные верны?",
            keyboard=kb.get_json()
        )
    finally:
        await release_lock(vk_id)


async def is_waiting_for_onboarding_data(message: Message) -> bool:
    if message.text and message.text.lower() in ["начать", "start", "/start", "сброс"]:
        return False
    state = await get_user_state(message.from_id)
    if not state:
        return False
    try:
        data = json.loads(state)
        step = data.get("step", "")
    except Exception:
        step = state
    return step == "waiting_for_onboarding_data"

@labeler.message(func=is_waiting_for_onboarding_data)
async def process_onboarding_data(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        user_text = message.text.strip()
        await message.answer("👁‍🗨 Анализирую состояние звезд...")
        await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")


        data = await extract_birth_data(user_text)

        if not data:
            await message.answer("Не удалось считать координаты Ваших звёзд. Напиши, пожалуйста, в формате: ДД.ММ.ГГГГ, Время, Город.")
            return

        date = data.get("date", "")
        time = data.get("time", "")
        city = data.get("city", "")

        if not date or not time or not city:
            await message.answer("Не удалось считать координаты. Напиши, пожалуйста, в формате: ДД.ММ.ГГГГ, Время, Город.")
            return

        await set_user_state(vk_id, json.dumps({
            "step": "confirm_data",
            "date": date,
            "time": time,
            "city": city
        }))

        verification_text = (
            f"🪐 Данные рождения распознаны:\n"
            f"Дата: {date}\n"
            f"Время: {time}\n"
            f"Город: {city}\n\n"
            f"Проверь точность. Алгоритм не прощает ошибок во времени и месте."
        )

        kb = Keyboard(inline=True)
        kb.add(Callback("✅ ДАННЫЕ ВЕРНЫ", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("🔄 ОШИБКА. ИСПРАВИТЬ", payload={"cmd": "edit_onboarding_data"}), color=KeyboardButtonColor.NEGATIVE)

        await message.answer(verification_text, keyboard=kb.get_json())

    finally:
        await release_lock(vk_id)

@labeler.message(text=["✦ Главное меню", "Главное меню", "В ГЛАВНОЕ МЕНЮ", "МЕНЮ", "НАЗАД", "✦ ГЛАВНОЕ МЕНЮ 🏠"])
async def back_to_main_menu(message: Message):
    vk_id = message.from_id

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
        except Exception:
            await message.answer(
                "ТВОИ ДАННЫЕ В СИСТЕМЕ. КУДА ДВИНЕМСЯ ДАЛЬШЕ?"
            )
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
    finally:
        await release_lock(vk_id)
