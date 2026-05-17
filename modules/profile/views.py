import re
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from vkbottle.bot import Message
from modules.bot_init import bot
from database import get_user, update_user, set_user_state, create_user
from cache import acquire_lock, release_lock
from modules.utils import (
    upload_local_photo,
    get_sections_keyboard,
    start_dynamic_typing,
    stop_dynamic_typing,
    ghost_edit,
    SKIN_ASSETS,
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
        text = f"ТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} Энергии звезд"

        typing_msg_id = await stop_dynamic_typing(peer_id)
        kb = Keyboard(inline=True)
        kb.add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
        kb.add(Callback("👤 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.PRIMARY)

        att = await upload_local_photo(bot.api, "uslugi/tariffs.jpg", peer_id=vk_id)

        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, message_id=typing_msg_id, keyboard=kb.get_json(), attachment=att)
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
        skin_filename = SKIN_ASSETS.get(active_skin, "o.png")
        photo = await upload_local_photo(bot.api, skin_filename, peer_id=vk_id)

        # Определение отображаемого имени персонажа
        from modules.utils.consts import SKIN_DISPLAY_NAMES
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

        birth_date = user.get("birth_date", "Неизвестно")
        birth_city = user.get("birth_city", "Неизвестно")
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

        # Динамическое приветствие от проводника
        greeting = "Я слежу за твоим прогрессом."
        if visit_streak > 5: greeting = "Твоя связь с матрицей впечатляет."
        if balance > 2000: greeting = "Твой энергетический потенциал огромен."
        if unlocked_count > 20: greeting = "Ты уже не просто гость, ты часть системы."

        profile_text = (
            "💳 ЛИЧНЫЙ ПРОФИЛЬ\n\n"
            f"👤 {first_name} | {rank}\n"
            f"💠 Уровень: {level}\n"
            f"📍 {birth_date} — {birth_city}\n"
            f"🔮 Твой проводник: {skin_display_name}\n\n"
            f"💬 {greeting}\n\n"
            f"✨ Баланс: {balance} Энергии звёзд\n"
            f"🔥 Стрик: {visit_streak} дней\n"
            f"🃏 Гримуар: {unlocked_count} из 78 карт\n"
            f"📊 ПРОГРЕСС: {progress_bar}\n\n"
            "Здесь ты можешь управлять своими данными, менять проводника "
            "и следить за ростом своей силы в матрице.\n\n"
            "📜 Публичная оферта:\n"
            "https://telegra.ph/PUBLICHNAYA-OFERTA-NA-OKAZANIE-INFORMACIONNO-RAZVLEKATELNYH-USLUG-05-04"
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
            progress_text = "Ты достиг абсолютного доминирования в Синдикате."
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
            "🕸 СИНДИКАТ 🕸\n\n"
            f"Твой текущий ранг: {rank}\n"
            f"Завербовано адептов: {syndicate_count}\n"
            f"Сгенерировано энергии: {syndicate_energy} ✨\n\n"
            f"{progress_text}\n\n"
            "Расширяй свою сеть. За каждого нового адепта ты получаешь 500 чистой Энергии звезд."
        )
        is_promo_used = purchased.get("promo_used", False)
        kb_json = get_syndicate_keyboard(is_promo_used)

        att = await upload_local_photo(bot.api, "uslugi/syndicate.jpg", peer_id=vk_id)

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
        group_id = "219181948"
        text = (
            "🕸 ТВОЯ ПЕРСОНАЛЬНАЯ ПЕЧАТЬ 🕸\n"
            "Используй её, чтобы расширить свой Синдикат.\n\n"
            f"💠 КОД: ПЕЧАТЬ-{vk_id}\n\n"
            "🔗 ПРЯМАЯ ССЫЛКА ДЛЯ ПРИЗЫВА:\n"
            f"https://vk.com/im?sel=-{group_id}&text=ПЕЧАТЬ-{vk_id}\n\n"
            "------------------\n"
            "КАК ЭТО РАБОТАЕТ:\n"
            "1. Отправь ссылку или код другу.\n"
            "2. Он переходит и активирует Печать.\n"
            "3. ТЫ получаешь +500 ✨ мгновенно.\n"
            "4. ОН получает +500 ✨ на старт.\n\n"
            "Призови 5 адептов, чтобы стать Теневым Кардиналом."
        )

        typing_msg_id = await stop_dynamic_typing(peer_id)
        kb = Keyboard(inline=True)
        kb.add(Callback("⬅️ НАЗАД В СИНДИКАТ", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.PRIMARY)
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
        await message.answer("Введи Печать (код), которую тебе передал Ведущий:", keyboard=kb_json)
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
        text = override_ref.strip().upper() if override_ref else message.text.strip().upper()
        match = re.match(r"^(ПРОМО|ПЕЧАТЬ)-(\d+)$", text)
        if not match:
            return
        referrer_id = int(match.group(2))
        user = await get_user(vk_id)
        is_new = False
        if not user:
            user = await create_user(vk_id, "", "", "")
            is_new = True
        purchased = user.get("purchased_sections", {})
        if purchased.get("promo_used"):
            await message.answer("Твоя матрица уже была усилена Печатью ранее. Путь открыт лишь однажды. Выстраивай свой личный Синдикат, чтобы получить больше энергии.")
            return
        if referrer_id == vk_id:
            await message.answer("Ты не можешь использовать свою собственную Печать.")
            return
        referrer = await get_user(referrer_id)
        if not referrer:
            await message.answer("Такой Печати не существует.")
            return
        user_balance = int(user.get("balance", 0) or 0) + 500
        referrer_balance = int(referrer.get("balance", 0) or 0) + 500
        purchased["promo_used"] = True
        await update_user(vk_id, {"balance": user_balance, "purchased_sections": purchased})
        ref_purchased = referrer.get("purchased_sections", {})
        ref_purchased["syndicate_count"] = ref_purchased.get("syndicate_count", 0) + 1
        ref_purchased["syndicate_energy"] = ref_purchased.get("syndicate_energy", 0) + 500
        await update_user(referrer_id, {"balance": referrer_balance, "purchased_sections": ref_purchased})
        await message.answer(f"ПЕЧАТЬ АКТИВИРОВАНА! Тебе начислено 500 Энергии звезд. Твой баланс: {user_balance} Энергии звезд")
        if is_new:
            from modules.registration import start_handler
            await start_handler(message, skip_lock=True)
        try:
            first_name = purchased.get("first_name")
            if not first_name:
                user_info = await bot.api.users.get(user_ids=[vk_id])
                if user_info:
                    first_name = user_info[0].first_name
                else:
                    first_name = "Адепт"
            push_msg = f"Твой Синдикат растет! Пользователь {first_name} подключился к твоей сети. Зачислено 500 Энергии звезд."
            if ref_purchased.get("syndicate_count", 0) == 5:
                push_msg += "\n\nТвой ранг повышен до: Теневой Кардинал! Теперь тебе открыты скрытые возможности."
            await bot.api.messages.send(peer_id=referrer_id, message=push_msg, random_id=0)
        except Exception as e:
            logger.error(f"Ignored Exception: {str(e)}")
    finally:
        await stop_dynamic_typing(message.peer_id)
        if not skip_lock:
            await release_lock(vk_id)


async def show_history_logic(
    vk_id: int,
    peer_id: int,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    """Отображение истории разборов"""
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user: return

        history = user.get("readings_history", [])
        if not history:
            text = "ТВОЙ СПИСОК ОТКРОВЕНИЙ ПОКА ПУСТ.\n\nЗакажи свой первый разбор в меню 'Услуги', чтобы он сохранился здесь."
        else:
            text = f"📜 ТВОИ ПРОШЛЫЕ РАЗБОРЫ ({len(history)})\n\nЗдесь хранятся все твои обращения к системе. Ты можешь перечитать их в любой момент."

        from modules.keyboards import get_history_inline_keyboard
        kb_json = get_history_inline_keyboard(history)

        att = await upload_local_photo(bot.api, "uslugi/history.jpg", peer_id=vk_id)

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

        real_idx = len(history) - 1 - idx
        if real_idx < 0: return

        item = history[real_idx]
        text = f"📜 {item.get('title')} от {item.get('date')}\n\n{item.get('text')}"

        kb = Keyboard(inline=True)
        kb.add(Callback("⬅️ НАЗАД В СПИСОК", payload={"cmd": "history_menu"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("🏠 ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

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

        text = (
            "⚙️ СИСТЕМНЫЕ НАСТРОЙКИ\n\n"
            "Здесь ты можешь управлять своим аккаунтом и подписками."
        )

        from modules.profile.keyboards import get_advanced_settings_keyboard
        kb_json = get_advanced_settings_keyboard(vk_id)

        att = await upload_local_photo(bot.api, "uslugi/settings.jpg", peer_id=vk_id)

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
            "Приветствую тебя, искатель. Здесь собраны ключи к пониманию того, как устроено наше пространство. "
            "Это не просто бот — это твой личный мост между звездами и реальностью.\n\n"
            "Выбери раздел, чтобы узнать больше о своей силе:"
        )

        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_main_keyboard
        kb_json = get_guide_main_keyboard()

        att = await upload_local_photo(bot.api, "uslugi/guide.jpg", peer_id=vk_id)

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
            "✨ ЭНЕРГИЯ И ДАРЫ\n\n"
            "Энергия звезд — это топливо для наших ритуалов. Она позволяет системе считывать твои вибрации. "
            "Курс обмена прост: 10 ✨ = 1 рубль.\n\n"
            "🤫 СЕКРЕТ ПРОВОДНИКА:\n"
            "Если ты заходишь в систему каждый день, твой дар растет. Стрик в 7 дней увеличит твой ежедневный бонус до 500 ✨. "
            "Не прерывай цикл, чтобы не потерять поток.\n\n"
            "Как получить энергию:\n"
            "• 700 ✨ — приветственный дар при первой синхронизации.\n"
            "• Ежедневно — забирай подарок в Главном меню.\n"
            "• Мой Круг — делись Печатью и получай по 500 ✨ за каждого адепта."
        )
        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_sub_keyboard
        kb_json = get_guide_sub_keyboard("💳 ПОПОЛНИТЬ", {"cmd": "profile_action", "action": "tariffs"})

        att = await upload_local_photo(bot.api, "uslugi/tariffs.jpg", peer_id=vk_id)
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
            "🔮 ГЛУБОКИЕ РАЗБОРЫ\n\n"
            "Это не просто текст. Это реальные расклады на колодах Таро, которые я проживаю для тебя. "
            "Мы объединяем древнюю мудрость карт и точность твоих астрологических данных.\n\n"
            "Что ты получаешь:\n"
            "✅ Глубокий PDF-отчет (сохраняется навсегда).\n"
            "✅ Детальный разбор ситуации по всем слоям матрицы.\n"
            "✅ Персональные советы от твоего Проводника.\n\n"
            "Это инвестиция в твое будущее. После каждого разбора твоя связь с системой становится крепче, а ответы — точнее."
        )
        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_sub_keyboard
        kb_json = get_guide_sub_keyboard("🛒 В КАТАЛОГ", {"cmd": "services_menu"})

        att = await upload_local_photo(bot.api, "uslugi/services.jpg", peer_id=vk_id)
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
            "🤝 МОЙ КРУГ (СИНДИКАТ)\n\n"
            "Твоя сила — в твоих последователях. В профиле ты найдешь свою уникальную 'Печать' (реферальный код).\n\n"
            "Как это работает:\n"
            "1. Передай Печать или ссылку новому адепту.\n"
            "2. При её активации вы ОБА мгновенно получите по 500 ✨.\n"
            "3. Твой ранг растет с каждым приглашенным. Призови 5 адептов, чтобы стать 'Теневым Кардиналом' и открыть скрытые возможности системы."
        )
        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_sub_keyboard
        kb_json = get_guide_sub_keyboard("🤝 В МОЙ КРУГ", {"cmd": "profile_action", "action": "syndicate"})

        att = await upload_local_photo(bot.api, "uslugi/syndicate.jpg", peer_id=vk_id)
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
            "🃏 ГРИМУАР И РАНГИ\n\n"
            "Каждый разбор открывает новую карту Таро. Всего в колоде 78 карт. "
            "Твой Гримуар в профиле — это летопись твоего духовного пути.\n\n"
            "Зачем повышать уровень:\n"
            "Чем выше твой ранг (от Неофита до Магистра Матрицы), тем более глубокие и редкие послания ты сможешь считывать. "
            "Твой уровень растет автоматически с каждой новой открытой картой и за регулярное посещение системы."
        )
        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.keyboards import get_guide_sub_keyboard
        kb_json = get_guide_sub_keyboard("📖 В ГРИМУАР", {"cmd": "profile_action", "action": "grimoire"})

        att = await upload_local_photo(bot.api, "uslugi/history.jpg", peer_id=vk_id)
        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, message_id=typing_msg_id, keyboard=kb_json, attachment=att)
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock:
            await release_lock(vk_id)
