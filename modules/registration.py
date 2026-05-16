import json
import asyncio
from loguru import logger
from vkbottle import Callback, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message

import asyncio
from ai_service import extract_birth_data, generate_text
from cache import acquire_lock, release_lock, redis_client
from database import (
    create_user,
    delete_user,
    get_user,
    get_user_state,
    set_user_state,
    update_user,
)
from modules.bot_init import bot
from modules.utils import (
    start_dynamic_typing,
    stop_dynamic_typing,
    ghost_edit,
    upload_local_photo,
    SKIN_ASSETS
)

labeler = BotLabeler()


# ==================== СБРОС ====================
@labeler.message(text=["СБРОС"])
async def reset_user_handler(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        await delete_user(vk_id)
        await set_user_state(vk_id, "")
        await message.answer("СИСТЕМА ОБНУЛЕНА. Напиши 'Начать' для теста с нуля.")
        logger.success(f"Пользователь {vk_id} полностью сброшен")
    except Exception as e:
        logger.error(f"Ошибка in reset_user_handler: {e}")
    finally:
        await release_lock(vk_id)


# ==================== ГЛАВНЫЙ СТАРТ ====================
@labeler.message(text=["Начать", "start", "/start"])
@labeler.message(payload={"command": "start"})
async def start_handler(message: Message, skip_lock: bool = False):
    vk_id = message.from_id

    # Проверка на реферальную ссылку (deep link)
    if hasattr(message, "ref") and message.ref and message.ref.upper().startswith(("ПЕЧАТЬ-", "ПРОМО-")) and not skip_lock:
        from modules.profile.views import apply_promo_logic
        await apply_promo_logic(vk_id, message, override_ref=message.ref)
        return

    # Интерактивный старт
    await start_dynamic_typing(bot.api, vk_id)
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
                birth_date=bdate or "",
                birth_time="12:00",
                birth_city=city or "",
                first_name=first_name
            )

        # Обновляем имя и пол если изменились
        if user:
            purchased = user.get("purchased_sections", {})
            purchased["first_name"] = first_name
            purchased["sex_val"] = sex
            await update_user(vk_id, {"purchased_sections": purchased})

        await stop_dynamic_typing(vk_id)

        welcome_text = (
            "✦ ИНИЦИАЦИЯ В МАТРИЦУ АНТИ-ТАР ✦\n\n"
            f"Приветствую, {first_name}. Я — АНТИ-ТАР. Твой проводник в мир, где алгоритмы встречаются с судьбой.\n\n"
            "Здесь нет места иллюзиям. Только чистый код твоей души и жесткие факты.\n\n"
            "Прежде чем мы начнем, выбери своего Проводника, который будет вести тебя через тернии матрицы:"
        )

        kb = Keyboard(inline=True)
        kb.add(Callback("💎 КИБЕР-ОЛЕСЯ", payload={"cmd": "choose_onboarding_skin", "skin": "Олеся Ивонченко"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("🌑 СЕРЬЕЗНЫЙ АСКЕТ", payload={"cmd": "choose_onboarding_skin", "skin": "Серьезный Аскет"}), color=KeyboardButtonColor.PRIMARY)

        # Загружаем фото Олеси для велком-месседжа
        att = await upload_local_photo(bot.api, SKIN_ASSETS["Олеся Ивонченко"], peer_id=vk_id)

        await message.answer(welcome_text, attachment=att, keyboard=kb.get_json())
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
            # Если по какой-то причине пользователя нет, создаем его (подстраховка)
            user = await create_user(vk_id=vk_id, birth_date="", birth_time="12:00", birth_city="", first_name="")
            if not user: return

        await update_user(vk_id, {"active_skin": skin})

        bdate = user.get("birth_date") or "Не указана"
        city = user.get("birth_city") or "Не указан"

        await set_user_state(
            vk_id,
            json.dumps({
                "step": "confirm_data",
                "date": bdate,
                "time": "12:00",
                "city": city
            })
        )

        kb = Keyboard(inline=True)
        kb.add(Callback("✅ ДАННЫЕ ВЕРНЫ", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("🔄 ИЗМЕНИТЬ", payload={"cmd": "edit_onboarding_data"}), color=KeyboardButtonColor.NEGATIVE)

        text = (
            f"Твой выбор принят. Теперь синхронизируем координаты твоего появления в системе.\n\n"
            f"Данные из профиля:\n"
            f"Дата рождения: {bdate}\n"
            f"Город рождения: {city}\n\n"
            "Алгоритмы требуют точности. Эти данные верны?"
        )

        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, keyboard=kb.get_json())
    except Exception as e:
        logger.error(f"Error in process_onboarding_skin_logic: {e}")

# ==================== ОЖИДАНИЕ ДАННЫХ РОЖДЕНИЯ ====================
async def is_waiting_for_onboarding_data(message: Message) -> bool:
    state = await get_user_state(message.from_id)
    if not state: return False
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
        # Ищем conv_id в состоянии, если он там есть
        state = await get_user_state(vk_id)
        conv_id = None
        try:
            data_state = json.loads(state)
            conv_id = data_state.get("conv_id")
        except: pass

        await start_dynamic_typing(bot.api, vk_id, conversation_message_id=conv_id)

        data = await extract_birth_data(user_text)
        await stop_dynamic_typing(vk_id)

        if not data:
            await message.answer("Не удалось считать координаты. Напиши в формате: ДД.ММ.ГГГГ, Время, Город.")
            return

        date = data.get("date", "")
        time = data.get("time", "")
        city = data.get("city", "")

        if not date or not time or not city:
            await message.answer("Не удалось считать координаты. Напиши в формате: ДД.ММ.ГГГГ, Время, Город.")
            return

        await set_user_state(
            vk_id,
            json.dumps({
                "step": "confirm_data",
                "date": date,
                "time": time,
                "city": city
            })
        )

        kb = Keyboard(inline=True)
        kb.add(Callback("✅ ДАННЫЕ ВЕРНЫ", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("🔄 ОШИБКА. ИСПРАВИТЬ", payload={"cmd": "edit_onboarding_data"}), color=KeyboardButtonColor.NEGATIVE)

        verification_text = (
            f"✦ КООРДИНАТЫ РАСПОЗНАНЫ ✦\n\n"
            f"Дата: {date}\n"
            f"Время: {time}\n"
            f"Город: {city}\n\n"
            "Проверь точность. Алгоритм не прощает ошибок."
        )

        typing_msg_id = await stop_dynamic_typing(vk_id)
        await ghost_edit(
            bot.api,
            message.peer_id,
            verification_text,
            conversation_message_id=conv_id,
            message_id=typing_msg_id,
            keyboard=kb.get_json()
        )

    except Exception as e:
        logger.error(f"Ошибка в process_onboarding_data: {e}")
        await message.answer("Произошла ошибка. Попробуй ещё раз.")
    finally:
        await release_lock(vk_id)

# ==================== ФИНАЛЬНЫЙ ТИЗЕР ====================

async def send_onboarding_teaser(vk_id: int, peer_id: int, conversation_message_id: int = None):
    user = await get_user(vk_id)
    if not user: return

    active_skin = user.get("active_skin", "olesya")
    core_profile = f"{user.get('birth_date')} {user.get('birth_time')} {user.get('birth_city')}"

    # Ритуал интеграции
    ritual_steps = [
        "🧬 Анализ генетического кода судьбы...",
        "🛰 Синхронизация с планетарными транзитами...",
        "🃏 Калибровка колоды под твою частоту...",
        "👁 Доступ к хроникам Акаши разрешен."
    ]

    for step in ritual_steps:
        await ghost_edit(bot.api, peer_id, f"✦ ИНИЦИАЦИЯ ✦\n\n{step}", conversation_message_id=conversation_message_id)
        await asyncio.sleep(1.5)

    await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)

    teaser_prompt = (
        f"Пользователь только что зарегистрировался. Его данные: {core_profile}. "
        f"Сгенерируй ОДНУ короткую, но шокирующе точную фразу о его главной теневой черте или таланте на основе даты рождения. "
        f"Это должен быть 'крючок', чтобы он захотел узнать больше. "
        f"Стиль: {active_skin}. Коротко, без приветствий. Без жирного шрифта."
    )

    teaser_text = await generate_text(teaser_prompt, skin=active_skin)
    await stop_dynamic_typing(peer_id)

    final_text = (
        "✦ ИНТЕГРАЦИЯ ЗАВЕРШЕНА ✦\n\n"
        f"{teaser_text}\n\n"
        "Твоя матрица теперь в системе. Тебе начислено 700 Энергии звезд для первого погружения.\n\n"
        "Куда направимся первым делом?"
    )

    from modules.keyboards import get_main_inline_keyboard, get_main_reply_keyboard
    kb_json = await get_main_inline_keyboard(vk_id, user)
    reply_kb = get_main_reply_keyboard(vk_id)

    await ghost_edit(bot.api, peer_id, final_text, conversation_message_id=conversation_message_id, keyboard=kb_json)
    # Отправляем reply-клавиатуру отдельным сообщением для фиксации интерфейса
    await bot.api.messages.send(peer_id=peer_id, message="Нижняя панель навигации активирована.", keyboard=reply_kb, random_id=0)

# ==================== ВОЗВРАТ В ГЛАВНОЕ МЕНЮ ====================
@labeler.message(text=["Главное меню", "В ГЛАВНОЕ МЕНЮ", "МЕНЮ", "НАЗАД"])
async def back_to_main_menu(message: Message):
    vk_id = message.from_id
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

        # Кэширование динамического статуса (чтобы не дергать AI на каждый чих)
        cache_key = f"dynamic_status:{vk_id}"
        cached_status = await redis_client.get(cache_key)
        if cached_status:
            status_phrase = cached_status
        else:
            # Раз в 6 часов или при первом входе генерим новый статус
            from ai_service import generate_text
            core_profile = f"{user.get('birth_date')} {user.get('birth_city')}"
            prompt = (
                f"Сгенерируй ОДНУ короткую (до 10 слов) загадочную фразу о текущем состоянии 'Матрицы' для пользователя. "
                f"Используй его данные: {core_profile}. Учитывай его уровень {level}. "
                f"Стиль: {active_skin}. Без приветствий. Без жирного шрифта. Без точек в конце."
            )
            try:
                dynamic_status = await generate_text(prompt, skin=active_skin)
                if dynamic_status and len(dynamic_status) < 100:
                    status_phrase = dynamic_status
                    await redis_client.set(cache_key, status_phrase, ex=21600) # 6 часов
            except: pass

        # Визуальный стрик (Лунный цикл)
        visit_streak = user.get("visit_streak", 0)
        moons = ["🌑", "🌘", "🌗", "🌖", "🌕", "✨", "🔥"]
        streak_visual = "".join(moons[i % len(moons)] if i < visit_streak else "○" for i in range(7))

        main_menu_text = (
            "✦ АНТИ-ТАР ✦\n\n"
            f"Привет, {first_name}!\n"
            f"Уровень {level} • {rank} ⭐ {balance} Энергии\n"
            f"Цикл: {streak_visual} ({visit_streak} дн.)\n\n"
            f"🔮 {status_phrase}"
        )

        await message.answer(
            main_menu_text,
            keyboard=kb_json
        )
        # Обновляем reply-клавиатуру при возврате в меню
        await message.answer("Интерфейс обновлен.", keyboard=get_main_reply_keyboard(vk_id))
    except Exception as e:
        logger.error(f"Ошибка в back_to_main_menu: {e}")
    finally:
        await release_lock(vk_id)
