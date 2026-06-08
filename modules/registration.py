import json
import asyncio
import re
from loguru import logger
from vkbottle import Callback, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message

from ai_service import generate_text, extract_birth_data
from cache import (
    acquire_lock, release_lock, redis_client,
    get_temp_birth_data, set_temp_birth_data
)
from database import (
    create_user,
    get_user,
    set_user_state,
    update_user,
)
from modules.bot_init import bot
from modules.utils import (
    get_fsm_step,
    start_dynamic_typing,
    stop_dynamic_typing,
    ghost_edit,
    upload_local_photo,
    SKIN_ASSETS,
    send_temp_message,
    delete_bot_message,
    get_last_bot_msg,
    set_last_bot_msg
)
from modules.utils.consts import MYSTIC_STATUS_PHRASES
import random

labeler = BotLabeler()


# ==================== СБРОС ====================
async def is_reset_command(message: Message) -> bool:
    if message.attachments or message.fwd_messages or message.reply_message:
        return False
    if not message.text:
        return False
    return message.text.lower().strip() in {"сброс", "reset", "обнулить", "начать заново"}

@labeler.message(func=is_reset_command)
async def reset_user_handler(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        # СБРОС: только очистка FSM и временных данных в Redis
        from cache import delete_temp_birth_data
        await delete_temp_birth_data(vk_id)
        await set_user_state(vk_id, "")

        await message.answer(
            "✨ ТВОЙ ПУТЬ ПЕРЕЗАГРУЖЕН ✨\n\n"
            "Текущее состояние и временные данные очищены. Твой профиль и баланс сохранены.\n"
            "Если ты застрял — теперь ты можешь начать диалог заново."
        )
        logger.info(f"Пользователь {vk_id} выполнил мягкий сброс (FSM/Redis)")
    except Exception as e:
        logger.error(f"Ошибка в reset_user_handler: {e}")
    finally:
        await release_lock(vk_id)


# ==================== ГЛАВНЫЙ СТАРТ ====================
@labeler.message(func=lambda m: m.text and m.text.lower() in ["начать", "start", "/start", "консоль", "console"])
@labeler.message(payload={"command": "start"})
async def start_handler(message: Message, skip_lock: bool = False):
    vk_id = message.from_id

    # КОНСОЛЬ: Редирект в админку для администратора
    if message.text and message.text.lower() in ["консоль", "console"]:
        from modules.utils import ADMIN_ID
        if vk_id == ADMIN_ID:
            from modules.admin import show_admin_main
            return await show_admin_main(message.peer_id)

    user = await get_user(vk_id)
    # Если пользователь уже зарегистрирован, отправляем в главное меню
    if user and user.get("is_registered"):
        # Удаляем сообщение пользователя
        asyncio.create_task(delete_bot_message(bot.api, message.peer_id, cmid=message.conversation_message_id))
        return await back_to_main_menu(message)

    # Проверка на реферальную ссылку (deep link)
    if hasattr(message, "ref") and message.ref and not skip_lock:
        from modules.profile.views import apply_promo_logic
        await apply_promo_logic(vk_id, message, override_ref=message.ref)
        # Мы не делаем return здесь, потому что apply_promo_logic сам вызовет start_handler или back_to_main_menu
        return

    # Интерактивный старт
    await start_dynamic_typing(bot.api, vk_id)
    # Удаляем старое меню, если оно было
    last_mid = await get_last_bot_msg(vk_id)
    if last_mid:
        await delete_bot_message(bot.api, vk_id, mid=last_mid)

    await asyncio.sleep(2) # Даем прочувствовать момент

    if not skip_lock and not await acquire_lock(vk_id):
        return

    try:
        users_info = await bot.api.users.get(
            user_ids=[vk_id], fields=["sex", "bdate", "city"]
        )
        first_name = ""
        sex = 0
        bdate = ""
        city = ""

        if users_info:
            info = users_info[0]
            first_name = info.first_name or ""
            sex = info.sex or 0
            bdate = info.bdate or ""
            if info.city and hasattr(info.city, "title"):
                city = info.city.title

        user = await get_user(vk_id)
        if not user:
            user = await create_user(
                vk_id=vk_id,
                first_name=first_name
            )
            # Сохраняем начальные данные в Redis на 24 часа
            if bdate or city:
                await set_temp_birth_data(vk_id, {
                    "date": bdate or "",
                    "time": "12:00",
                    "city": city or ""
                })

            # Трекинг регистрации
            from database import add_event
            metadata = {"first_name": first_name}
            if hasattr(message, "ref") and message.ref:
                metadata["source"] = "referral"
                metadata["ref_code"] = message.ref
            else:
                metadata["source"] = "organic"

            await add_event(vk_id, "registration", metadata)

        # Обновляем имя и пол если изменились
        if user:
            purchased = user.get("purchased_sections", {})
            purchased["first_name"] = first_name
            purchased["sex_val"] = sex
            await update_user(vk_id, {"purchased_sections": purchased})

        await stop_dynamic_typing(vk_id)

        welcome_text = (
            "✨ ДОБРО ПОЖАЛОВАТЬ В АНТИ-ТАР ✨\n\n"
            f"Здравствуй, {first_name}. Я — твой проводник в мир самопознания и глубоких инсайтов.\n\n"
            "Здесь мы отбросим лишнее, чтобы услышать истинный голос твоего сердца и шепот звезд.\n\n"
            "Выбери того, кто будет оберегать тебя на этом пути. Сейчас тебе доступны трое сильных проводников, "
            "которые помогут тебе вскрыть слои реальности."
        )

        kb = Keyboard(inline=True)
        kb.add(Callback("🌸 ОЛЕСЯ ИВОНЧЕНКО", payload={"cmd": "choose_onboarding_skin", "skin": "olesya"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("🕯 АЛЕКСАНДР ШЕППС", payload={"cmd": "choose_onboarding_skin", "skin": "sheps_alex"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("🧠 ВОЛЬФ МЕССИНГ", payload={"cmd": "choose_onboarding_skin", "skin": "messing"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("🎭 ЗАЛ ПРОРОКОВ", payload={"cmd": "skin_page", "idx": 0}), color=KeyboardButtonColor.SECONDARY)

        # Загружаем фото Олеси для велком-месседжа
        att = await upload_local_photo(bot.api, SKIN_ASSETS["olesya"], peer_id=vk_id)

        msg_id = await message.answer(welcome_text, attachment=att, keyboard=kb.get_json())
        await set_last_bot_msg(vk_id, msg_id)
        await set_user_state(vk_id, "onboarding_skin_selection")

    except Exception as e:
        logger.error(f"Ошибка в start_handler: {e}")
        await message.answer("Произошла ошибка при инициализации. Попробуй ещё раз.")
    finally:
        if not skip_lock:
            await release_lock(vk_id)
        await stop_dynamic_typing(vk_id)


# ==================== ВЫБОР СКИНА И ПРОВЕРКА ДАННЫХ ====================

async def process_onboarding_skin_logic(vk_id: int, peer_id: int, skin: str, conversation_message_id: int = None):
    try:
        user = await get_user(vk_id)
        if not user:
            user = await create_user(vk_id=vk_id, first_name="")
            if not user: return

        await update_user(vk_id, {"active_skin": skin})

        # Получаем временные данные из Redis
        temp_data = await get_temp_birth_data(vk_id) or {}
        bdate = temp_data.get("date")
        city = temp_data.get("city")

        # Если данных не хватает (пустые или отсутствуют), отправляем на ручной ввод
        if not bdate or not city or bdate == "Не указана" or city == "Не указан":
            state_dict = await get_fsm_step(vk_id) or {}
            state_dict.update({"step": "waiting_birth_date", "conv_id": conversation_message_id})
            await set_user_state(vk_id, json.dumps(state_dict))
            text = (
                "Твой выбор согревает сердце. Чтобы я могла настроить твою личную карту звездного неба, "
                "мне нужны твои данные.\n\n"
                "Напиши свою ДАТУ рождения (например, 15.04.1990):"
            )
            return await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id)

        state_dict = await get_fsm_step(vk_id) or {}
        state_dict.update({
            "step": "confirm_data",
            "date": bdate,
            "time": temp_data.get("time", "12:00"),
            "city": city
        })
        await set_user_state(vk_id, json.dumps(state_dict))

        kb = Keyboard(inline=True)
        kb.add(Callback("✅ ДАННЫЕ ВЕРНЫ", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("🔄 ИЗМЕНИТЬ", payload={"cmd": "edit_onboarding_data"}), color=KeyboardButtonColor.NEGATIVE)

        text = (
            f"Твой выбор согревает сердце. Теперь давай настроим твою личную карту звездного неба.\n\n"
            f"Твои данные:\n"
            f"☾ Дата рождения: {bdate}\n"
            f"☾ Город рождения: {city}\n\n"
            "Скажи, всё ли верно указано?"
        )

        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, keyboard=kb.get_json())
    except Exception as e:
        logger.error(f"Error in process_onboarding_skin_logic: {e}")

# ==================== ПОШАГОВЫЙ СБОР ДАННЫХ ====================

async def send_registration_confirmation(message: Message, state_dict: dict):
    kb = Keyboard(inline=True)
    kb.add(Callback("✅ ДАННЫЕ ВЕРНЫ", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("🔄 ИЗМЕНИТЬ", payload={"cmd": "edit_onboarding_data"}), color=KeyboardButtonColor.NEGATIVE)

    text = (
        f"✨ ТВОЯ ЗВЕЗДНАЯ КАРТА ПОЧТИ ГОТОВА ✨\n\n"
        f"☾ Дата: {state_dict.get('date')}\n"
        f"☾ Время: {state_dict.get('time', '12:00')}\n"
        f"☾ Город: {state_dict.get('city')}\n\n"
        "Посмотри внимательно, всё ли правильно? Точность важна для верного предсказания."
    )
    await message.answer(text, keyboard=kb.get_json())

async def is_waiting_birth_date(message: Message) -> bool:
    if not message.text or any(message.text.startswith(e) for e in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_birth_date"

def validate_birth_year(date_str: str) -> bool:
    """Проверка адекватности года рождения (1920-2026)"""
    try:
        match = re.search(r"(\d{4})", date_str)
        if match:
            year = int(match.group(1))
            return 1920 <= year <= 2026
    except:
        pass
    return True # Если не нашли год, пропускаем для ИИ-обработки

@labeler.message(func=is_waiting_birth_date)
async def process_birth_date(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        text = message.text.strip()
        state_dict = await get_fsm_step(vk_id) or {}

        # Проверка на адекватность года
        if not validate_birth_year(text):
            await message.answer("🌌 Звезды не видят людей из этого времени. Пожалуйста, введи корректный год рождения (1920-2026):")
            return

        # 1. Быстрая проверка регуляркой
        if re.match(r"^\d{2}\.\d{2}\.\d{4}$", text):
            state_dict.update({"step": "waiting_birth_time", "date": text})
            await set_user_state(vk_id, json.dumps(state_dict))
            kb = Keyboard(inline=True).add(Callback("⏳ НЕ ПОМНЮ", payload={"cmd": "skip_birth_time"}), color=KeyboardButtonColor.SECONDARY)
            await message.answer(
                f"☾ {text} — прекрасный день для начала пути.\n\n"
                "Теперь шепни мне ВРЕМЯ своего рождения (например, 14:30).\n"
                "Если время скрыто в тумане прошлого — просто нажми кнопку ниже.",
                keyboard=kb.get_json()
            )
            return

        # 2. Умное распознавание (Fallback на ИИ)
        data = await extract_birth_data(text)

        if data.get("is_complete"):
            # Проверка года после ИИ
            if not validate_birth_year(data["date"]):
                await message.answer("🌌 Звезды не видят людей из будущего или столь далекого прошлого. Пожалуйста, введи корректную дату рождения:")
                return

            state_dict.update({
                "step": "confirm_data",
                "date": data["date"],
                "time": data["time"],
                "city": data["city"]
            })
            await set_user_state(vk_id, json.dumps(state_dict))
            await send_registration_confirmation(message, state_dict)
        else:
            found_date = data.get("date")
            found_city = data.get("city")
            found_time = data.get("time")

            if found_date:
                if not validate_birth_year(found_date):
                    await message.answer("🌌 Звезды не видят людей из этого времени. Пожалуйста, введи корректную дату рождения:")
                    return
                state_dict["date"] = found_date
            if found_city: state_dict["city"] = found_city
            if found_time and found_time != "12:00": state_dict["time"] = found_time

            if found_date and not found_city:
                state_dict["step"] = "waiting_birth_city"
                await set_user_state(vk_id, json.dumps(state_dict))
                await message.answer(f"Я зафиксировал твою дату рождения ({found_date})! Теперь, пожалуйста, напиши город, в котором ты родился, чтобы Оракул точно рассчитал твои дома.")
            elif found_city and not found_date:
                state_dict["step"] = "waiting_birth_date"
                await set_user_state(vk_id, json.dumps(state_dict))
                await message.answer(f"Город {found_city} принят. Теперь напиши дату своего рождения (ДД.ММ.ГГГГ):")
            elif found_date and found_city:
                state_dict["step"] = "confirm_data"
                await set_user_state(vk_id, json.dumps(state_dict))
                await send_registration_confirmation(message, state_dict)
            else:
                await message.answer("Я не смогла разобрать данные. Пожалуйста, напиши дату своего рождения в формате ДД.ММ.ГГГГ:")
    finally:
        await release_lock(vk_id)

async def is_waiting_birth_time(message: Message) -> bool:
    if not message.text or any(message.text.startswith(e) for e in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_birth_time"

@labeler.message(func=is_waiting_birth_time)
async def process_birth_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        text = message.text.strip()
        state_dict = await get_fsm_step(vk_id) or {}

        if re.match(r"^\d{2}:\d{2}$", text):
            state_dict.update({"step": "waiting_birth_city", "time": text})
            await set_user_state(vk_id, json.dumps(state_dict))
            await message.answer("🕯 Время зафиксировано. И последний штрих — в каком ГОРОДЕ ты увидел свой первый звездный свет?")
            return

        # Fallback на ИИ
        data = await extract_birth_data(text)
        found_time = data.get("time")
        found_city = data.get("city")

        if found_time and found_time != "12:00":
            state_dict["time"] = found_time
            if found_city:
                state_dict.update({"step": "confirm_data", "city": found_city})
                await set_user_state(vk_id, json.dumps(state_dict))
                await send_registration_confirmation(message, state_dict)
            else:
                state_dict["step"] = "waiting_birth_city"
                await set_user_state(vk_id, json.dumps(state_dict))
                await message.answer(f"Время {found_time} зафиксировано. А в каком городе ты родился?")
        else:
            await message.answer("Пожалуйста, введи время в формате ЧЧ:ММ (например, 14:30) или нажми кнопку 'НЕ ПОМНЮ':")
    finally:
        await release_lock(vk_id)

async def is_waiting_birth_city(message: Message) -> bool:
    if not message.text or any(message.text.startswith(e) for e in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_birth_city"

@labeler.message(func=is_waiting_birth_city)
async def process_birth_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        text = message.text.strip()
        state_dict = await get_fsm_step(vk_id) or {}

        # Для города мы всегда можем попробовать нормализацию через ИИ,
        # но если это одно слово, можно и так принять.
        # Однако ИИ может исправить "Питер" на "Санкт-Петербург", что нам нужно.
        data = await extract_birth_data(text)
        city_text = data.get("city") or text # Если ИИ не нашел, берем сырой текст

        state_dict.update({
            "step": "confirm_data",
            "city": city_text
        })
        if "time" not in state_dict: state_dict["time"] = "12:00"

        await set_user_state(vk_id, json.dumps(state_dict))
        await send_registration_confirmation(message, state_dict)
    finally:
        await release_lock(vk_id)

# ==================== ФИНАЛЬНЫЙ ТИЗЕР ====================

async def send_onboarding_teaser(vk_id: int, peer_id: int, conversation_message_id: int = None):
    user = await get_user(vk_id)
    if not user: return

    active_skin = user.get("active_skin", "olesya")

    # Берем данные из Redis
    temp_data = await get_temp_birth_data(vk_id) or {}
    core_profile = f"{temp_data.get('date')} {temp_data.get('time')} {temp_data.get('city')}"

    # Ритуал интеграции
    ritual_steps = [
        "✨ Настраиваюсь на твою уникальную энергию...",
        "🌙 Изучаю положение звезд в момент твоего рождения...",
        "🔮 Перемешиваю карты для твоего первого расклада...",
        "🕯 Вхожу в поток твоего предназначения..."
    ]

    for step in ritual_steps:
        await ghost_edit(bot.api, peer_id, f"✨ ТВОЕ ПУТЕШЕСТВИЕ НАЧИНАЕТСЯ ✨\n\n{step}", conversation_message_id=conversation_message_id)
        await asyncio.sleep(1.5)

    await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)

    teaser_prompt = (
        f"Пользователь только что зарегистрировался. Его данные: {core_profile}. "
        f"Сгенерируй ОДНУ короткую, нежную, но попадающую в самое сердце фразу о его главной силе или таланте на основе даты рождения. "
        f"Это должен быть светлый 'инсайт', чтобы он почувствовал твою глубину. "
        f"Стиль: {active_skin}. Коротко, без приветствий. Без жирного шрифта."
    )

    teaser_text = await generate_text(teaser_prompt, skin=active_skin)
    await stop_dynamic_typing(peer_id)

    final_text = (
        "✨ ТВОЙ ПУТЬ ОТКРЫТ ✨\n\n"
        f"{teaser_text}\n\n"
        "Я дарю тебе 700 Энергии звезд для первых шагов к познанию себя.\n\n"
        "С чего начнем наш разговор?"
    )

    from modules.keyboards import get_main_inline_keyboard, get_main_reply_keyboard
    kb_json = await get_main_inline_keyboard(vk_id, user)
    reply_kb = get_main_reply_keyboard(vk_id)

    await ghost_edit(bot.api, peer_id, final_text, conversation_message_id=conversation_message_id, keyboard=kb_json)
    # Ежедневный бонус при первом открытии
    from modules.utils.logic import check_and_give_daily_bonus
    await check_and_give_daily_bonus(vk_id, user, peer_id)

    # Отправляем reply-клавиатуру отдельным сообщением для фиксации интерфейса
    # И удаляем сообщение "вам начислено 700 энергии" (teaser_text)
    await send_temp_message(bot.api, peer_id, "Твоя панель навигации активирована ✨", delay=3, keyboard=reply_kb)

# ==================== ВОЗВРАТ В ГЛАВНОЕ МЕНЮ ====================
@labeler.message(func=lambda m: m.text and m.text.lower() in ["главное меню", "в главное меню", "меню", "назад", "🏠 главное меню"] and not m.attachments)
async def back_to_main_menu(message: Message):
    vk_id = message.from_id
    # Удаляем сообщение пользователя
    asyncio.create_task(delete_bot_message(bot.api, message.peer_id, cmid=message.conversation_message_id))

    await set_user_state(vk_id, "")

    if not await acquire_lock(vk_id):
        return

    try:
        user = await get_user(vk_id)
        if not user:
            await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
            return

        from modules.keyboards import get_main_inline_keyboard, get_main_reply_keyboard
        kb_json = await get_main_inline_keyboard(vk_id, user)

        first_name = user.get("first_name") or "Адепт"
        balance = int(user.get("balance", 0) or 0)
        active_skin = user.get("active_skin", "olesya")

        from modules.utils.logic import calculate_user_rank
        level, rank = calculate_user_rank(user)

        from modules.utils.consts import SKIN_STATUS_PHRASES
        status_phrase = SKIN_STATUS_PHRASES.get(active_skin, "Система готова.")

        # Кэширование динамического статуса (случайный из базы)
        cache_key = f"dynamic_status:{vk_id}"
        cached_status = await redis_client.get(cache_key)
        if cached_status:
            status_phrase = cached_status
        else:
            try:
                status_phrase = random.choice(MYSTIC_STATUS_PHRASES)
                await redis_client.set(cache_key, status_phrase, ex=21600) # 6 часов
            except: pass

        # Визуальный стрик (Лунный цикл)
        visit_streak = user.get("visit_streak", 0)
        moons = ["🌑", "🌘", "🌗", "🌖", "🌕", "✨", "🔥"]
        streak_visual = "".join(moons[i % len(moons)] if i < visit_streak else "○" for i in range(7))

        main_menu_text = (
            "✨ АНТИ-ТАР ✨\n\n"
            f"Здравствуй, {first_name}!\n"
            f"Твой уровень: {level} • {rank} ✨ {balance} Энергии\n"
            f"Лунный цикл: {streak_visual} ({visit_streak} дн.)\n\n"
            f"🔮 {status_phrase}"
        )

        att = await upload_local_photo(bot.api, "uslugi/main_menu.jpeg", peer_id=vk_id)

        await ghost_edit(
            bot.api,
            message.peer_id,
            main_menu_text,
            keyboard=kb_json,
            attachment=att,
            delete_last=True
        )
        # Обновляем reply-клавиатуру при возврате в меню
        await send_temp_message(bot.api, message.peer_id, "Я обновила твое меню ✨", delay=3, keyboard=get_main_reply_keyboard(vk_id))
    except Exception as e:
        logger.error(f"Ошибка в back_to_main_menu: {e}")
    finally:
        await release_lock(vk_id)
