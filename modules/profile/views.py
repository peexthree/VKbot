import re
import random
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from vkbottle.bot import Message
from modules.bot_init import bot
from database import get_user, update_user, set_user_state
from cache import acquire_lock, release_lock
from modules.utils import (
    upload_local_photo,
    get_sections_keyboard,
    start_dynamic_typing,
    stop_dynamic_typing,
    ghost_edit,
)
from modules.profile.keyboards import get_syndicate_keyboard, get_cancel_seal_keyboard, get_profile_keyboard


async def show_balance_logic(
    vk_id: int,
    peer_id: int,
    message: Message = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        user = await get_user(vk_id)
        if not user:
            await ghost_edit(bot.api, peer_id, "ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.", conversation_message_id=conversation_message_id)
            return
        balance = int(user.get("balance", 0) or 0)
        text = (
            f"✨ ТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} Энергии звезд\n\n"
            "Энергия звезд необходима для проведения глубоких ритуалов и получения ответов от матрицы.\n\n"
            "💡 СОВЕТ ПРОВОДНИКА:\n"
            "Приобретать энергию пакетами гораздо выгоднее. Пакеты по 10 000 и 50 000 ✨ дают максимальную силу по лучшей цене."
        )

        typing_msg_id = await stop_dynamic_typing(peer_id)

        from modules.keyboards import vertical_kb
        kb = vertical_kb([
            ("💳 ПОПОЛНИТЬ БАЛАНС", {"cmd": "tariff_page", "idx": 0}, KeyboardButtonColor.POSITIVE),
            ("👤 ПРОФИЛЬ", "profile_menu", KeyboardButtonColor.PRIMARY),
            ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
        ])

        att = await upload_local_photo(bot.api, "uslugi/tariffs.jpeg", peer_id=vk_id)

        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, message_id=typing_msg_id, keyboard=kb, attachment=att)
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def show_profile_logic(
    vk_id: int,
    peer_id: int,
    message: Message = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    """Премиум-профиль — точно такой вид, как ты показал"""
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        user = await get_user(vk_id)
        if not user:
            text = "❌ Не удалось найти ваш профиль. Напишите 'Начать'"
            await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id)
            return

        # Фото текущего скина (маскот никогда не используется)
        active_skin = user.get("active_skin", "olesya")
        from modules.utils.consts import SKIN_VISUALS, SKIN_DISPLAY_NAMES
        skin_filename = "uslugi/" + SKIN_VISUALS.get(active_skin, "ol.jpeg")
        photo = await upload_local_photo(bot.api, skin_filename, peer_id=vk_id)

        # Определение отображаемого имени персонажа
        skin_display_name = SKIN_DISPLAY_NAMES.get(active_skin, active_skin)

        # Данные
        first_name = user.get("first_name") or "Адепт"
        if first_name == "Адепт":
            try:
                user_info = await bot.api.users.get(user_ids=[vk_id])
                if user_info:
                    first_name = user_info[0].first_name
            except Exception:
                pass

        # Получаем данные рождения из Redis
        from cache import get_temp_birth_data
        birth_data = await get_temp_birth_data(vk_id) or {}

        b_date = birth_data.get("date", "⏳ Данные истекли")
        b_city = birth_data.get("city", "")

        birth_display = f"{b_date} — {b_city}" if b_city else b_date

        balance = int(user.get("balance", 0) or 0)
        visit_streak = user.get("visit_streak", 0)

        # Расчет уровня Адепта
        from modules.utils.logic import calculate_user_rank
        level, rank = calculate_user_rank(user)

        # Прогресс по реальным открытым картам
        unlocked_cards = user.get("unlocked_cards", {})
        unlocked_count = len(unlocked_cards)
        progress = min(10, int((unlocked_count / 78) * 10))
        progress_bar = "█" * progress + "░" * (10 - progress)

        destiny_info = ""
        destiny_data = user.get("destiny_card_data")
        if destiny_data:
            from cards_data import get_card_data
            c_data = get_card_data(destiny_data.get("card_id", "0"))
            destiny_info = f"⭐ МОЯ КАРТА СУДЬБЫ: {c_data.get('name', 'Неизвестно')}\n"

        # Динамическое приветствие от проводника
        greeting = "Я слежу за твоим прогрессом."
        if visit_streak > 5: greeting = "Твоя связь с матрицей впечатляет."
        if balance > 2000: greeting = "Твой энергетический потенциал огромен."
        if unlocked_count > 20: greeting = "Ты уже не просто гость, ты часть системы."

        # Извлекаем статистику
        purchased = user.get("purchased_sections", {})
        clicks = purchased.get("stats_clicks", 0)
        total_seconds = purchased.get("stats_total_seconds", 0)
        total_rubles = purchased.get("stats_total_rubles", 0)

        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        time_str = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"

        # Определение статуса Шепота звезд
        expires_str = user.get("transit_sub_expires_at")
        whisper_status = "Не активна"
        if expires_str:
            import datetime as dt
            try:
                # В Supabase может быть ISO с Z или без. Преобразуем к TZ-aware UTC для сравнения.
                exp_date = dt.datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                now_utc = dt.datetime.now(dt.timezone.utc)
                if exp_date > now_utc:
                    whisper_status = f"до {exp_date.strftime('%d.%m.%Y')}"
            except Exception:
                pass

        profile_text = (
            "💳 ЛИЧНЫЙ ПРОФИЛЬ\n\n"
            f"👤 {first_name} | {rank}\n"
            f"💠 Уровень: {level} | 🔥 Стрик: {visit_streak} дней\n"
            f"📍 {birth_display}\n\n"
            f"{destiny_info}"
            f"💬 {greeting}\n\n"
            f"📊 ТВОЯ СТАТИСТИКА:\n"
            f"🛰 Шепот звезд: {whisper_status}\n"
            f"🔘 Нажатий: {clicks} | ⏳ В пути: {time_str}\n"
            f"💰 Внесено: {total_rubles} RUB\n\n"
            f"✨ БАЛАНС: {balance} Энергии звезд\n"
            f"🃏 ГРИМУАР: {unlocked_count}/78 [{progress_bar}]"
        )

        keyboard = get_profile_keyboard()

        # Stop typing and get message_id used if any
        typing_msg_id = await stop_dynamic_typing(peer_id)

        # Если у нас уже было сообщение от тайпинга или нам передали conv_id — редактируем
        await ghost_edit(
            bot.api,
            peer_id,
            profile_text,
            conversation_message_id=conversation_message_id,
            message_id=typing_msg_id,
            attachment=photo,
            keyboard=keyboard
        )
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def god_mode_logic(vk_id: int, message: Message, skip_lock: bool = False):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, message.peer_id)
        user = await get_user(vk_id)
        if not user:
            await message.answer("Сначала напиши 'Начать'")
            return
        new_balance = int(user.get("balance", 0) or 0) + 100000
        await update_user(vk_id, {"balance": new_balance})
        kb_json = await get_sections_keyboard(vk_id, user)
        await message.answer("ЛАЙН ПОДАЛ ГОЛОС. ВАМ НАЧИСЛЕНО 100 000 ЭНЕРГИИ ЗВЕЗД.", keyboard=kb_json)
    finally:
        await stop_dynamic_typing(message.peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def syndicate_dashboard_logic(
    vk_id: int,
    peer_id: int,
    message: Message = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        user = await get_user(vk_id)
        if not user:
            return
        purchased = user.get("purchased_sections", {})
        syndicate_count = purchased.get("syndicate_count", 0)
        syndicate_energy = purchased.get("syndicate_energy", 0)

        from modules.utils.logic import get_syndicate_rank
        rank = get_syndicate_rank(syndicate_count)

        if syndicate_count >= 10:
            progress_text = "Ты достиг абсолютного доминирования в своем кругу."
        elif syndicate_count >= 5:
            left = 10 - syndicate_count
            progress_text = f"До статуса Теневой Архитектор осталось {left} адепт(а)."
        elif syndicate_count >= 3:
            left = 5 - syndicate_count
            progress_text = f"До статуса Теневой Кардинал осталось {left} адепт(а)."
        elif syndicate_count >= 1:
            left = 3 - syndicate_count
            progress_text = f"До статуса Мастер Вербовки осталось {left} адепт(а)."
        else:
            progress_text = "До статуса Вербовщик остался 1 адепт."

        text = (
            "👥 МОЙ КРУГ 👥\n\n"
            f"Твой текущий ранг: {rank}\n"
            f"Призвано адептов: {syndicate_count}\n"
            f"Сгенерировано энергии: {syndicate_energy} ✨\n\n"
            f"{progress_text}\n\n"
            "Расширяй свой круг влияния. За каждого нового адепта ты получаешь 500 чистой Энергии звезд."
        )
        is_promo_used = purchased.get("promo_used", False)
        kb_json = get_syndicate_keyboard(is_promo_used)

        att = await upload_local_photo(bot.api, "uslugi/syndicate.jpeg", peer_id=vk_id)

        typing_msg_id = await stop_dynamic_typing(peer_id)
        await ghost_edit(
            bot.api,
            peer_id,
            text,
            conversation_message_id=conversation_message_id,
            message_id=typing_msg_id,
            keyboard=kb_json,
            attachment=att
        )
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def get_seal_logic(
    vk_id: int,
    peer_id: int,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        user = await get_user(vk_id)
        if not user: return

        purchased = user.get("purchased_sections", {})
        cipher = purchased.get("shadow_cipher")
        if not cipher:
            from modules.utils.logic import generate_shadow_cipher
            cipher = generate_shadow_cipher()
            purchased["shadow_cipher"] = cipher
            await update_user(vk_id, {"purchased_sections": purchased})

        group_id = "219181948"
        text = (
            "✨ ТВОЙ ТЕНЕВОЙ ШИФР ✨\n"
            "Используй его, чтобы призвать новых адептов в систему.\n\n"
            f"💠 ШИФР: {cipher}\n\n"
            "🔗 ССЫЛКА ДЛЯ ПРИЗЫВА (vk.me):\n"
            f"https://vk.me/club{group_id}?ref={cipher}\n\n"
            "------------------\n"
            "КАК ЭТО РАБОТАЕТ:\n"
            "1. Передай шифр или ссылку другу.\n"
            "2. Он активирует её при входе в систему.\n"
            "3. ТЫ получаешь +500 ✨ мгновенно.\n"
            "4. ОН получает +500 ✨ на старт.\n\n"
            "Призови 5 адептов, чтобы стать Теневым Кардиналом."
        )

        typing_msg_id = await stop_dynamic_typing(peer_id)
        kb = Keyboard(inline=True)
        kb.add(Callback("⬅️ МОЙ КРУГ", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
        await ghost_edit(
            bot.api,
            peer_id,
            text,
            conversation_message_id=conversation_message_id,
            message_id=typing_msg_id,
            keyboard=kb.get_json()
        )
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def enter_seal_logic(vk_id: int, message: Message, skip_lock: bool = False):
    await set_user_state(vk_id, "waiting_for_seal")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, message.peer_id)
        kb_json = get_cancel_seal_keyboard()
        await message.answer("Введи Теневой Шифр, который тебе передал другой адепт:", keyboard=kb_json)
    finally:
        await stop_dynamic_typing(message.peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def cancel_seal_logic(vk_id: int, peer_id: int, message: Message, skip_lock: bool = False):
    await set_user_state(vk_id, "")
    await syndicate_dashboard_logic(vk_id, peer_id, message, skip_lock=skip_lock)


async def apply_promo_logic(vk_id: int, message: Message, skip_lock: bool = False, override_ref: str = None):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, message.peer_id)
        ref_text = override_ref.strip() if override_ref else message.text.strip()
        text = ref_text.upper()

        # Проверка на автопостинг (ref=autopost_topic_name)
        if ref_text.lower().startswith("autopost_"):
            topic_name = ref_text[9:] # Отрезаем "autopost_"
            from database.autoposter import record_post_click
            await record_post_click(vk_id, topic_name)
            logger.info(f"Зафиксирован клик по автопосту: {topic_name} от пользователя {vk_id}")
            # После фиксации клика продолжаем обычный старт
            from modules.registration import start_handler
            return await start_handler(message, skip_lock=True)

        # Поддержка старых кодов (на всякий случай) и новых шифров
        match_old = re.match(r"^(ПРОМО|ПЕЧАТЬ)-(\d+)$", text)
        cipher = None
        referrer = None

        if match_old:
            referrer_id = int(match_old.group(2))
            referrer = await get_user(referrer_id)
        else:
            # Пытаемся найти как теневой шифр (6 символов)
            cipher = text.replace("REF=", "") # На случай если передали с префиксом ссылки
            from database import get_user_by_cipher
            referrer = await get_user_by_cipher(cipher)

        user = await get_user(vk_id)
        is_new = False
        if not user:
            from database import create_user
            user = await create_user(vk_id, "", "", "")
            is_new = True

        purchased = user.get("purchased_sections", {})
        if purchased.get("promo_used"):
            if not override_ref: # Не спамим если это автоматический deep link
                await message.answer("Твоя матрица уже была усилена Шифром ранее. Путь открыт лишь однажды. Выстраивай свой личный круг, чтобы получить больше энергии.")
            return

        if not referrer:
            if not override_ref:
                await message.answer("Матрица не узнает этот шифр. Проверь символы или попроси актуальный код у друга.")
            return

        referrer_id = referrer.get("vk_id")
        if referrer_id == vk_id:
            if not override_ref:
                from vkbottle import Keyboard, KeyboardButtonColor, Callback
                kb = Keyboard(inline=True)
                kb.add(Callback("👥 МОЙ КРУГ", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.PRIMARY)
                kb.row()
                kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

                await message.answer(
                    "Ты не можешь использовать свой собственный Шифр. Матрица не терпит саморепликации.\n\n"
                    "Перешли свой шифр другу — когда он активирует его, вы оба получите по 500 Энергии звезд! ✨",
                    keyboard=kb.get_json()
                )
            return

        user_balance = int(user.get("balance", 0) or 0) + 500
        referrer_balance = int(referrer.get("balance", 0) or 0) + 500

        purchased["promo_used"] = True
        await update_user(vk_id, {"balance": user_balance, "purchased_sections": purchased})

        ref_purchased = referrer.get("purchased_sections", {})
        ref_purchased["syndicate_count"] = ref_purchased.get("syndicate_count", 0) + 1
        ref_purchased["syndicate_energy"] = ref_purchased.get("syndicate_energy", 0) + 500
        await update_user(referrer_id, {"balance": referrer_balance, "purchased_sections": ref_purchased})

        if ref_purchased["syndicate_count"] >= 5:
            from modules.skins import unlock_skin
            await unlock_skin(bot.api, referrer_id, "fluffy")

        # Трекинг успешного использования шифра
        from database import add_event
        await add_event(vk_id, "referral_activated", {"referrer_id": referrer_id, "cipher": cipher or "old_style"})

        await message.answer(f"✨ ШИФР ПРИНЯТ! ✨\nТебе начислено 500 Энергии звезд за вступление в круг. Твой баланс: {user_balance} ✨")

        if is_new:
            from modules.registration import start_handler
            await start_handler(message, skip_lock=True)
        else:
            # Если пользователь уже был, но просто ввел код - возвращаем в меню
            from modules.registration import back_to_main_menu
            await back_to_main_menu(message)

        try:
            user_info = await bot.api.users.get(user_ids=[vk_id])
            first_name = user_info[0].first_name if user_info else "Адепт"

            push_msg = f"🌟 Твой круг растет! Пользователь {first_name} активировал твой Теневой Шифр. Зачислено 500 Энергии звезд."
            if ref_purchased.get("syndicate_count", 0) == 5:
                push_msg += "\n\nТвой ранг повышен до: Теневой Кардинал! Теперь тебе открыты скрытые возможности."

            await bot.api.messages.send(peer_id=referrer_id, message=push_msg, random_id=random.getrandbits(63))
        except Exception as e:
            logger.error(f"Push notification failed: {str(e)}")
    finally:
        await stop_dynamic_typing(message.peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def show_history_logic(
    vk_id: int,
    peer_id: int,
    page: int = 0,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    """Отображение истории разборов с пагинацией"""
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user: return

        history = user.get("readings_history", [])

        # Специальный заголовок для Карты Судьбы (только на 0 странице)
        destiny_text = ""
        destiny_data = user.get("destiny_card_data")
        if page == 0 and destiny_data:
            from cards_data import get_card_data
            c_data = get_card_data(destiny_data.get("card_id", "0"))
            destiny_text = f"⭐ МОЯ КАРТА СУДЬБЫ: {c_data.get('name')}\n------------------\n\n"

        if not history and not destiny_data:
            text = "ТВОЙ СПИСОК ОТКРОВЕНИЙ ПОКА ПУСТ.\n\nЗакажи свой первый разбор в меню 'Услуги', чтобы он сохранился здесь."
        else:
            text = f"{destiny_text}📜 ТВОИ ПРОШЛЫЕ РАЗБОРЫ ({len(history)})\n\nЗдесь хранятся все твои обращения к системе."

        from modules.keyboards import get_history_inline_keyboard
        # Нужно передать в клавиатуру инфу о карте судьбы чтобы она была первой
        kb_json = get_history_inline_keyboard(history, destiny_data=destiny_data, page=page)

        att = await upload_local_photo(bot.api, "uslugi/history.jpeg", peer_id=vk_id)

        await ghost_edit(
            bot.api,
            peer_id,
            text,
            conversation_message_id=conversation_message_id,
            keyboard=kb_json,
            attachment=att
        )
    finally:
        if not skip_lock:
            await release_lock(vk_id)


async def show_history_item_logic(
    vk_id: int,
    peer_id: int,
    idx: int,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    """Отображение конкретного разбора из истории"""
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user: return

        history = user.get("readings_history", [])
        if not history or idx >= len(history):
            return

        # История хранится в прямом порядке, но отображаем мы последние сначала (через [::-1])
        # Чтобы правильно сопоставить индекс, нужно учесть это.
        # Однако проще передавать индекс в прямом списке.
        # В get_history_inline_keyboard я использую enumerate(history[-8:][::-1])
        # Это значит idx 0 соответствует последнему элементу и т.д.

        if idx == -1:
            destiny_data = user.get("destiny_card_data")
            if not destiny_data: return
            item = {
                "title": "⭐ КАРТА СУДЬБЫ",
                "date": destiny_data.get("date"),
                "text": destiny_data.get("text")
            }
        else:
            # Индекс idx уже соответствует rev_history из get_history_inline_keyboard
            rev_history = history[::-1]
            if idx < 0 or idx >= len(rev_history):
                return
            item = rev_history[idx]
        text = f"📜 {item.get('title')} от {item.get('date')}\n\n{item.get('text')}"

        kb = Keyboard(inline=True)
        kb.add(Callback("⬅️ НАЗАД В СПИСОК", payload={"cmd": "history_menu"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

        await ghost_edit(
            bot.api,
            peer_id,
            text,
            conversation_message_id=conversation_message_id,
            keyboard=kb.get_json()
        )
    finally:
        if not skip_lock:
            await release_lock(vk_id)


async def show_advanced_settings_logic(
    vk_id: int,
    peer_id: int,
    message: Message = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    """Отображение расширенных настроек и системы"""
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)

        user = await get_user(vk_id)
        purchased = user.get("purchased_sections", {}) if user else {}
        is_muted = purchased.get("whisper_muted", False)

        text = (
            "⚙️ СИСТЕМНЫЕ НАСТРОЙКИ\n\n"
            "Здесь ты можешь управлять своим аккаунтом и подписками."
        )

        from modules.profile.keyboards import get_advanced_settings_keyboard
        kb_json = get_advanced_settings_keyboard(vk_id, is_muted=is_muted)

        att = await upload_local_photo(bot.api, "uslugi/settings.jpeg", peer_id=vk_id)

        typing_msg_id = await stop_dynamic_typing(peer_id)
        await ghost_edit(
            bot.api,
            peer_id,
            text,
            conversation_message_id=conversation_message_id,
            message_id=typing_msg_id,
            keyboard=kb_json,
            attachment=att
        )
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def show_guide_logic(
    vk_id: int,
    peer_id: int,
    message: Message = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    """Главный экран Путеводителя"""
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        text = (
            "📖 ПУТЕВОДИТЕЛЬ ПО МАТРИЦЕ\n\n"
            "Приветствую тебя в сакральном хранилище знаний. Здесь собраны ключи к пониманию того, как устроено наше пространство. "
            "Это не просто бот — это мощный инструмент анализа твоей судьбы, объединяющий древнюю мудрость и современные алгоритмы.\n\n"
            "Выбери интересующий тебя раздел, чтобы раскрыть потенциал системы:"
        )

        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_main_keyboard
        kb_json = get_guide_main_keyboard()

        att = await upload_local_photo(bot.api, "uslugi/guide.jpeg", peer_id=vk_id)

        await ghost_edit(
            bot.api,
            peer_id,
            text,
            conversation_message_id=conversation_message_id,
            message_id=typing_msg_id,
            keyboard=kb_json,
            attachment=att
        )
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def show_guide_energy_logic(vk_id: int, peer_id: int, conversation_message_id: int = None, skip_lock: bool = False):
    """Раздел Энергии в Путеводителе"""
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        text = (
            "✨ ЭНЕРГИЯ И ДАРЫ ЗВЕЗД\n\n"
            "Энергия — это эквивалент твоего внимания и намерения в нашей системе. Она необходима для проведения сложных вычислений и взаимодействия с AI-модулями.\n\n"
            "💎 ЦЕННОСТЬ:\n"
            "Курс фиксирован: 10 ✨ = 1 рубль.\n\n"
            "🔋 СПОСОБЫ ПОЛУЧЕНИЯ:\n"
            "• ПРИВЕТСТВЕННЫЙ ДАР: 700 ✨ ты получаешь сразу после синхронизации данных.\n"
            "• ЕЖЕДНЕВНЫЙ ЦИКЛ: Заходи в систему каждые 24 часа. Стрик посещений увеличивает твой бонус до 500 ✨ в день.\n"
            "• СИНДИКАТ: Приглашай друзей. Каждый новый адепт приносит тебе 500 ✨, а ему дает мощный старт.\n"
            "• ПРЯМАЯ ПОДПИТКА: Ты всегда можешь пополнить баланс через VK Pay."
        )
        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_sub_keyboard
        kb_json = get_guide_sub_keyboard("💳 ПОПОЛНИТЬ", {"cmd": "profile_action", "action": "tariffs"})

        att = await upload_local_photo(bot.api, "uslugi/tariffs.jpeg", peer_id=vk_id)
        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, message_id=typing_msg_id, keyboard=kb_json, attachment=att)
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def show_guide_services_logic(vk_id: int, peer_id: int, conversation_message_id: int = None, skip_lock: bool = False):
    """Раздел Услуг в Путеводителе"""
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        text = (
            "🔮 ГЛУБОКИЕ РАЗБОРЫ И СЕРВИСЫ\n\n"
            "Наши услуги разделены на несколько ключевых направлений для полного анализа твоей жизни:\n\n"
            "🔴 ПРЕНИУМ-АНАЛИЗ:\n"
            "• ❤️ СИНАСТРИЯ: Глубокий разбор отношений. Магия вашего союза.\n"
            "• ✨ ХИРОМАНТИЯ: Анализ линий ладоней через зрение AI.\n"
            "• 🌙 СОННИК: Толкование снов на языке архетипов Юнга.\n\n"
            "🟠 СЛОИ МАТРИЦЫ (Твоя натальная карта):\n"
            "• 🔥 СТРАСТЬ: Твоя сексуальность и желания.\n"
            "• 💰 ИЗОБИЛИЕ: Твой финансовый код и путь к богатству.\n"
            "• 👹 ТЕНЬ: Работа с подсознательными блоками.\n"
            "• 🧭 ПУТЬ: Твое главное предназначение.\n\n"
            "🟡 ОРАКУЛ И ТАРО:\n"
            "• 🔮 ВОПРОС ЗВЕЗДАМ: Прямой ответ на твой запрос.\n"
            "• 🃏 КАРТА ДНЯ: Твой бесплатный навигатор на сегодня."
        )
        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_sub_keyboard
        kb_json = get_guide_sub_keyboard("🛒 В КАТАЛОГ", {"cmd": "services_menu"})

        att = await upload_local_photo(bot.api, "uslugi/services.jpeg", peer_id=vk_id)
        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, message_id=typing_msg_id, keyboard=kb_json, attachment=att)
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def show_guide_syndicate_logic(vk_id: int, peer_id: int, conversation_message_id: int = None, skip_lock: bool = False):
    """Раздел Синдиката в Путеводителе"""
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        text = (
            "🤝 МОЙ КРУГ: СИЛА В ЕДИНСТВЕ\n\n"
            "Твое влияние в системе измеряется количеством адептов в твоем кругу. В профиле ты найдешь свой персональный 'Теневой Шифр'.\n\n"
            "📈 ПРИВИЛЕГИИ:\n"
            "1. ОБЮДНЫЙ БОНУС: За каждого приглашенного ты и твой друг получаете по 500 ✨.\n"
            "2. ИЕРАРХИЯ: Призывай больше людей, чтобы повышать свой ранг в системе.\n"
            "3. РАНГИ:\n"
            "• Вербовщик (1 адепт)\n"
            "• Мастер Вербовки (3 адепта)\n"
            "• Теневой Кардинал (5 адептов)\n"
            "• Теневой Архитектор (10 адептов)\n\n"
            "Высшие ранги получают доступ к закрытым тестам и эксклюзивным Проводникам в Зале пророков."
        )
        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_sub_keyboard
        kb_json = get_guide_sub_keyboard("🤝 В МОЙ КРУГ", {"cmd": "profile_action", "action": "syndicate"})

        att = await upload_local_photo(bot.api, "uslugi/syndicate.jpeg", peer_id=vk_id)
        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, message_id=typing_msg_id, keyboard=kb_json, attachment=att)
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def show_guide_grimoire_logic(vk_id: int, peer_id: int, conversation_message_id: int = None, skip_lock: bool = False):
    """Раздел Гримуара в Путеводителе"""
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        text = (
            "🃏 ГРИМУАР И ТВОЙ ПУТЬ\n\n"
            "Гримуар — это твоя личная коллекция открытых карт Таро. Каждая карта, полученная в ходе разборов, навсегда сохраняется здесь.\n\n"
            "🌌 СИСТЕМА РАНГОВ:\n"
            "Твой уровень (Level) растет за счет:\n"
            "• Получения новых разборов.\n"
            "• Открытия уникальных карт (всего их 78).\n"
            "• Регулярной активности в системе.\n\n"
            "🎖 ТВОЙ СТАТУС:\n"
            "От 'Неофита' до 'Магистра Матрицы'. Чем выше уровень, тем более 'умные' и глубокие ответы генерирует AI, подстраиваясь под твой накопленный опыт и энергетику."
        )
        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_sub_keyboard
        kb_json = get_guide_sub_keyboard("📖 В ГРИМУАР", {"cmd": "profile_action", "action": "grimoire"})

        att = await upload_local_photo(bot.api, "uslugi/history.jpeg", peer_id=vk_id)
        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, message_id=typing_msg_id, keyboard=kb_json, attachment=att)
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)
