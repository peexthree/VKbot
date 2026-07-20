import json
import random
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from vkbottle.bot import Message
from modules.bot_init import bot
from database import get_user, update_user, set_user_state
from cache import acquire_lock, release_lock
from modules.utils import upload_local_photo, ghost_edit
from modules.profile.keyboards import (
    get_settings_keyboard,
    get_reset_confirm_keyboard
)

async def _send_skins_page(
    vk_id: int,
    peer_id: int,
    purchased_skins: list[str],
    idx: int,
    edit_msg_id: int | None,
    user: dict = None
):
    # Категории: 1 (базовые), 2 (премиум), 3 (ачивки)
    categories = {
        "olesya": 1, "sheps_alex": 1, "messing": 1,
        "guzeeva": 2, "cherevatov": 2, "nostradamus": 2, "rasputin": 2, "kaliostro": 2, "blinovskaya": 2, "professor": 2,
        "fluffy": 3, "vanga": 3, "ai_mom": 3, "honest_oracle": 3, "saint_germain": 3, "pythia": 3, "freud": 3, "jack_sparrow": 3, "cleopatra": 3, "anubis": 3
    }

    from modules.utils.consts import SKIN_DISPLAY_NAMES, SKIN_VISUALS, CHARACTER_DESCRIPTIONS

    ordered_skins = [
        "olesya", "sheps_alex", "messing",
        "guzeeva", "cherevatov", "nostradamus", "rasputin", "kaliostro", "blinovskaya", "professor",
        "fluffy", "vanga", "ai_mom", "honest_oracle", "saint_germain", "pythia", "freud", "jack_sparrow", "cleopatra", "anubis"
    ]

    total_items = len(ordered_skins)
    page = idx % total_items
    s_key = ordered_skins[page]

    name = SKIN_DISPLAY_NAMES.get(s_key, s_key)
    filename = SKIN_VISUALS.get(s_key, "o.png")
    cat = categories.get(s_key, 1)
    is_owned = s_key in purchased_skins or cat == 1

    # Формирование описания
    desc_data = CHARACTER_DESCRIPTIONS.get(s_key, {})
    full_name = desc_data.get("name", name).upper()
    concept = desc_data.get("concept", "").replace("—", "-")
    style = desc_data.get("style", "").replace("—", "-")
    effect = desc_data.get("effect", "").replace("—", "-")

    # Чистим заголовки внутри текста, если они есть
    concept_text = concept.split(":", 1)[-1].strip() if ":" in concept else concept
    style_text = style.split(":", 1)[-1].strip() if ":" in style else style
    effect_text = effect.split(":", 1)[-1].strip() if ":" in effect else effect

    message_text = (
        f"🎭 ЗАЛ ПРОРОКОВ [{page + 1}/{total_items}]\n\n"
        f"👤 {full_name}\n\n"
        f"✨ КОНЦЕПЦИЯ: {concept_text}\n\n"
        f"🎭 СТИЛЬ: {style_text}\n\n"
        f"⚡ ЭФФЕКТ: {effect_text}"
    )

    # Клавиатура
    kb = Keyboard(inline=True)

    # Row 1: Action
    if is_owned:
        kb.add(Callback("✅ ВЫБРАТЬ", payload={"cmd": "set_skin", "skin": s_key}), color=KeyboardButtonColor.POSITIVE)
    else:
        if cat == 2:
            kb.add(Callback("💎 КУПИТЬ (1500 ✨)", payload={"cmd": "buy_skin", "skin": s_key}), color=KeyboardButtonColor.PRIMARY)
        elif cat == 3:
            label = "🔒 КАК ОТКРЫТЬ?"
            if user:
                if s_key == "fluffy":
                    curr, total = user.get("active_referrals_count", 0) or 0, 5
                    label = f"🔒 УСЛОВИЯ ({curr}/{total})"
                elif s_key == "vanga":
                    curr, total = user.get("visit_streak", 0) or 0, 7
                    label = f"🔒 УСЛОВИЯ ({curr}/{total})"
                elif s_key == "ai_mom":
                    curr, total = user.get("rituals_count", 0) or 0, 30
                    label = f"🔒 УСЛОВИЯ ({curr}/{total})"
                elif s_key == "pythia":
                    curr, total = user.get("dreams_analyzed_count", 0) or 0, 10
                    label = f"🔒 УСЛОВИЯ ({curr}/{total})"
                elif s_key == "freud":
                    curr, total = user.get("compatibility_partners_count", 0) or 0, 3
                    label = f"🔒 УСЛОВИЯ ({curr}/{total})"
                elif s_key == "cleopatra":
                    curr, total = user.get("used_skins_count", 0) or 0, 3
                    label = f"🔒 УСЛОВИЯ ({curr}/{total})"
                elif s_key == "anubis":
                    from modules.utils.logic import calculate_user_rank
                    level, _ = calculate_user_rank(user)
                    label = f"🔒 УСЛОВИЯ ({level}/5)"

            kb.add(Callback(label, payload={"cmd": "skin_quest", "skin": s_key}), color=KeyboardButtonColor.SECONDARY)

    # Row 2: Navigation
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "skins_page", "page": page - 1}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback(f"{page + 1}/{total_items}", payload={"cmd": "skins_page", "page": page}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("ДАЛЕЕ ➡️", payload={"cmd": "skins_page", "page": page + 1}), color=KeyboardButtonColor.SECONDARY)

    # Row 3: Settings
    kb.row()
    kb.add(Callback("⚙️ НАСТРОЙКИ", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.PRIMARY)

    photo = await upload_local_photo(bot.api, f"uslugi/{filename}", peer_id=vk_id)

    try:
        await ghost_edit(
            bot.api,
            peer_id=peer_id,
            message=message_text,
            attachment=photo,
            keyboard=kb.get_json(),
            conversation_message_id=edit_msg_id
        )
    except Exception as e:
        logger.error(f"Error sending skin page: {e}")

async def settings_handler_logic(
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
        user = await get_user(vk_id)
        balance = user.get("balance", 0) if user else 0
        from modules.utils.consts import SKIN_DISPLAY_NAMES
        active_skin = user.get("active_skin", "olesya")
        char_name = SKIN_DISPLAY_NAMES.get(active_skin, "Проводник")
        purchased = user.get("purchased_sections", {})
        is_muted = purchased.get("whisper_muted", False)
        text = (
            "⚙️ НАСТРОЙКИ\n"
            f"✨ Баланс: {balance} Энергии звезд\n\n"
            f"Здесь ты можешь управлять своим аккаунтом и Проводником в Зале пророков ({char_name})."
        )
        kb_json = get_settings_keyboard(is_muted=is_muted, vk_id=vk_id)
        att = await upload_local_photo(bot.api, "uslugi/settings.jpeg", peer_id=vk_id)
        await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, keyboard=kb_json, attachment=att)
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def settings_change_data_logic(vk_id: int, message: Message, skip_lock: bool = False):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await set_user_state(vk_id, json.dumps({"step": "waiting_birth_date"}))
        kb = Keyboard(inline=True).add(Callback("ОТМЕНА", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.NEGATIVE)
        await bot.api.messages.send(
            peer_id=message.peer_id,
            message="Для калибровки звездного пути напиши свою ДАТУ рождения (например, 15.04.1990):",
            keyboard=kb.get_json(),
            random_id=random.getrandbits(63)
        )
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def settings_cancel_subscription_logic(vk_id: int, message: Message, skip_lock: bool = False):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await message.answer("Ваш аккаунт не имеет активных рекуррентных подписок. Все платежи разовые. Для прекращения получения транзитов просто не пополняйте баланс. Отвязка карт не требуется по ФЗ №376-ФЗ.")
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def settings_reset_account_logic(vk_id: int, message: Message, skip_lock: bool = False):
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await set_user_state(vk_id, json.dumps({"step": "waiting_reset_confirm"}))
        kb_json = get_reset_confirm_keyboard()
        await message.answer(
            "⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс в системе. Вы уверены?",
            keyboard=kb_json
        )
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def confirm_reset_account_logic(vk_id: int, message: Message, skip_lock: bool = False):
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        # Очищаем только историю и теги
        await update_user(vk_id, {
            "readings_history": [],
            "tags": [],
            "core_profile": ""
        })
        # Удаляем данные из Redis
        from cache import clear_all_pii
        await clear_all_pii(vk_id)
        await set_user_state(vk_id, "")
        await message.answer("Твои личные данные и история полностью стерты. Твой путь чист, но сила звезд (баланс) осталась с тобой.")
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def settings_choose_character_logic(
    vk_id: int,
    peer_id: int,
    message: Message = None,
    skip_lock: bool = False,
    idx: int = 0,
    edit_msg_id: int = None
):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user:
            msg = "ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'."
            await ghost_edit(bot.api, peer_id, msg, conversation_message_id=edit_msg_id)
            return

        purchased_skins = user.get("purchased_skins", [])

        await _send_skins_page(
            vk_id=vk_id,
            peer_id=peer_id,
            purchased_skins=purchased_skins,
            idx=idx,
            edit_msg_id=edit_msg_id,
            user=user
        )
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def process_skin_action_logic(
    vk_id: int,
    peer_id: int,
    message: Message = None,
    skip_lock: bool = False,
    payload: dict = None,
    conversation_message_id: int = None
):
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user:
            return

        if not payload and message:
            try:
                payload = json.loads(message.payload)
            except Exception:
                payload = {}

        if not payload:
            return

        action = payload.get("cmd")
        target_skin = payload.get("skin")

        purchased_skins = user.get("purchased_skins", [])
        free_skins = ["olesya", "sheps_alex", "messing"]
        balance = int(user.get("balance", 0) or 0)

        if action == "set_skin":
            if target_skin in free_skins or target_skin in purchased_skins:
                purchased = user.get("purchased_sections", {})
                used_skins = purchased.get("used_skins", [])
                counted_skins = purchased.get("counted_skins", []) # Новый список для учета прогресса с нуля
                updates = {"active_skin": target_skin}

                if target_skin not in used_skins:
                    used_skins.append(target_skin)
                    purchased["used_skins"] = used_skins

                if target_skin not in counted_skins:
                    counted_skins.append(target_skin)
                    purchased["counted_skins"] = counted_skins
                    updates["used_skins_count"] = (user.get("used_skins_count", 0) or 0) + 1

                updates["purchased_sections"] = purchased
                await update_user(vk_id, updates)

                # Проверка на Клеопатру
                if len(used_skins) >= 3:
                    if user.get("birth_date") and user.get("birth_time") and user.get("birth_city"):
                        from modules.skins import unlock_skin
                        await unlock_skin(bot.api, vk_id, "cleopatra")

                from modules.profile.views import show_profile_logic
                await show_profile_logic(vk_id, peer_id, message, skip_lock=True, conversation_message_id=conversation_message_id)
            else:
                msg = "Этот персонаж недоступен. Сначала купите его."
                await ghost_edit(bot.api, peer_id, msg, conversation_message_id=conversation_message_id)

        elif action == "buy_skin":
            if target_skin in purchased_skins:
                from modules.profile.views import show_profile_logic
                await show_profile_logic(vk_id, peer_id, message, skip_lock=True, conversation_message_id=conversation_message_id)
                return

            price = 1500
            if balance >= price:
                new_balance = balance - price
                purchased_skins.append(target_skin)

                purchased = user.get("purchased_sections", {})
                used_skins = purchased.get("used_skins", [])
                counted_skins = purchased.get("counted_skins", [])
                updates = {
                    "balance": new_balance,
                    "purchased_skins": purchased_skins,
                    "active_skin": target_skin
                }

                if target_skin not in used_skins:
                    used_skins.append(target_skin)
                    purchased["used_skins"] = used_skins

                if target_skin not in counted_skins:
                    counted_skins.append(target_skin)
                    purchased["counted_skins"] = counted_skins
                    updates["used_skins_count"] = (user.get("used_skins_count", 0) or 0) + 1

                updates["purchased_sections"] = purchased
                await update_user(vk_id, updates)
                from modules.skins import send_trigger_message
                await send_trigger_message(bot.api, vk_id, target_skin)
                from modules.profile.views import show_profile_logic
                await show_profile_logic(vk_id, peer_id, message, skip_lock=True, conversation_message_id=conversation_message_id)
            else:
                msg = f"Недостаточно Энергии звезд. Цена: {price}.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} Энергии звезд."
                await ghost_edit(bot.api, peer_id, msg, conversation_message_id=conversation_message_id)
    finally:
        if not skip_lock:
            await release_lock(vk_id)
