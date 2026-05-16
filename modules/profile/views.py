import datetime
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
        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, message_id=typing_msg_id, keyboard=kb.get_json())
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

        profile_text = (
            "💳 ЛИЧНЫЙ ПРОФИЛЬ\n\n"
            f"👤 {first_name} | {rank}\n"
            f"💠 Уровень: {level}\n"
            f"📍 {birth_date} — {birth_city}\n"
            f"🔮 Твой проводник: {skin_display_name}\n\n"
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
        if syndicate_count >= 5:
            rank = "Теневой Кардинал"
            progress_text = "Ты достиг вершины синдиката."
        elif syndicate_count >= 1:
            rank = "Вербовщик"
            left = 5 - syndicate_count
            progress_text = f"До статуса Теневой Кардинал осталось {left} адепт(а)."
        else:
            rank = "Одиночка"
            progress_text = "До статуса Вербовщик остался 1 адепт."
        text = (
            "🕸 СИНДИКАТ 🕸\n\n"
            f"Твой текущий ранг: {rank}\n"
            f"Завербовано адептов: {syndicate_count}\n"
            f"Сгенерировано энергии: {syndicate_energy} ✨\n\n"
            f"{progress_text}\n\n"
            "Расширяй свою сеть. За каждого нового адепта ты получаешь 500 чистой Энергии звезд."
        )
        is_veteran = False
        created_at_str = user.get("created_at")
        if created_at_str:
            created_at = datetime.datetime.fromisoformat(created_at_str)
            now = datetime.datetime.now(datetime.timezone.utc)
            if (now - created_at).total_seconds() / 3600 > 24:
                is_veteran = True
        if purchased.get("promo_used"):
            is_veteran = True
        kb_json = get_syndicate_keyboard(is_veteran)

        typing_msg_id = await stop_dynamic_typing(peer_id)
        await ghost_edit(
            bot.api,
            peer_id,
            text,
            conversation_message_id=conversation_message_id,
            message_id=typing_msg_id,
            keyboard=kb_json
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
        is_veteran = False
        created_at_str = user.get("created_at")
        if created_at_str:
            created_at = datetime.datetime.fromisoformat(created_at_str)
            now = datetime.datetime.now(datetime.timezone.utc)
            if (now - created_at).total_seconds() / 3600 > 24:
                is_veteran = True
        purchased = user.get("purchased_sections", {})
        if purchased.get("promo_used"):
            is_veteran = True
        if is_veteran:
            await message.answer("Доступ отклонен. Твоя матрица уже давно интегрирована в систему. Печать призыва работает только для новых адептов. Выстраивай свой личный Синдикат.")
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


async def show_guide_logic(
    vk_id: int,
    peer_id: int,
    message: Message = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)
        text = (
            "ПУТЕВОДИТЕЛЬ ПО СИСТЕМЕ\n"
            "Здесь собраны ответы на все вопросы.\n\n"
            "Энергообмен: Вся система работает на Энергии звезд. 10 Энергии звезд равны 1 рублю. Ты можешь копить энергию или покупать ее.\n\n"
            "Как получать энергию в дар:\n\n"
            "Ежедневный дар: Заходи ко мне каждый день и открывай Главное меню. Я буду начислять тебе 100 Энергии звезд.\n\n"
            "Приветственный дар: Ты получаешь 700 Энергии звезд при регистрации.\n\n"
            "Синдикат: В разделе Мой профиль есть кнопка Синдикат. Передай Печать призыва новому адепту, и вы оба получите по 500 Энергии звезд.\n\n"
            "Как открывать тайны: Перейди в Услуги, листай карточки и жми Купить. Если энергии не хватит, система сама рассчитает доплату. После покупки я выдам тебе личный PDF-файл.\n\n"
            "Карты и Гримуар: После каждой покупки ты вытягиваешь новую карту. Она навсегда сохранится в твоем Гримуаре в профиле."
        )

        typing_msg_id = await stop_dynamic_typing(peer_id)
        kb = Keyboard(inline=True)
        kb.add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
        kb.add(Callback("👤 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.PRIMARY)
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
