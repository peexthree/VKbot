import json
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from vkbottle.bot import Message
from modules.bot_init import bot
from database import get_user, update_user, set_user_state
from cache import acquire_lock, release_lock
from modules.utils import SKIN_ASSETS, upload_local_photo, ghost_edit
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
):
    # Категории: 1 (базовые), 2 (премиум), 3 (ачивки)
    categories = {
        "olesya": 1, "sheps_alex": 1, "messing": 1,
        "guzeeva": 2, "cherevatov": 2, "nostradamus": 2, "rasputin": 2, "kaliostro": 2, "blinovskaya": 2, "professor": 2,
        "fluffy": 3, "vanga": 3, "ai_mom": 3, "honest_oracle": 3, "saint_germain": 3, "pythia": 3, "freud": 3, "jack_sparrow": 3, "cleopatra": 3, "anubis": 3
    }

    from modules.utils.consts import SKIN_DISPLAY_NAMES, SKIN_VISUALS

    ordered_skins = [
        "olesya", "sheps_alex", "messing",
        "guzeeva", "cherevatov", "nostradamus", "rasputin", "kaliostro", "blinovskaya", "professor",
        "fluffy", "vanga", "ai_mom", "honest_oracle", "saint_germain", "pythia", "freud", "jack_sparrow", "cleopatra", "anubis"
    ]

    ITEMS_PER_PAGE = 5
    total_items = len(ordered_skins)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    page = idx
    if page < 0:
        page = total_pages - 1
    elif page >= total_pages:
        page = 0

    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_skins = ordered_skins[start_idx:end_idx]

    from vkbottle.tools import TemplateElement
    from vkbottle import Keyboard, KeyboardButtonColor
    import asyncio

    elements = []
    for s_key in current_skins:
        name = SKIN_DISPLAY_NAMES.get(s_key, s_key)
        filename = SKIN_VISUALS.get(s_key, "o.png")
        cat = categories.get(s_key, 1)

        is_owned = s_key in purchased_skins or cat == 1

        title = name if is_owned else f"🔒 {name}"
        desc = ""

        button_payload = {}
        button_label = ""
        button_color = KeyboardButtonColor.SECONDARY

        if is_owned:
            button_label = "✅ Выбрать"
            button_color = KeyboardButtonColor.POSITIVE
            button_payload = {"cmd": "set_skin", "skin": s_key}
        else:
            if cat == 2:
                button_label = "💎 Купить (1500 ✨)"
                button_color = KeyboardButtonColor.PRIMARY
                button_payload = {"cmd": "buy_skin", "skin": s_key}
            elif cat == 3:
                button_label = "🔒 Как открыть?"
                button_color = KeyboardButtonColor.SECONDARY
                button_payload = {"cmd": "skin_quest", "skin": s_key}

        photo = await upload_local_photo(bot.api, f"uslugi/{filename}", peer_id=vk_id)
        if photo and photo.startswith("photo"):
            p_id = photo.replace("photo", "")
            # Убедимся что формат Owner_ID_Media_ID
            element_buttons = [{"action": {"type": "callback", "label": button_label, "payload": json.dumps(button_payload)}, "color": button_color.value}]
            elements.append({
                "title": title,
                "description": desc or " ",
                "photo_id": p_id,
                "buttons": element_buttons,
                "action": {"type": "open_photo"}
            })

    # Используем carousel
    carousel_template = {
        "type": "carousel",
        "elements": elements
    }

    nav_kb = Keyboard(inline=True)
    if total_pages > 1:
        nav_kb.add(Callback("⬅️", payload={"cmd": "skins_page", "page": page - 1}), color=KeyboardButtonColor.SECONDARY)
        nav_kb.add(Callback(f"{page + 1}/{total_pages}", payload={"cmd": "skins_page", "page": page}), color=KeyboardButtonColor.SECONDARY)
        nav_kb.add(Callback("Далее ➡️", payload={"cmd": "skins_page", "page": page + 1}), color=KeyboardButtonColor.SECONDARY)
        nav_kb.row()
    nav_kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

    header_text = f"🎭 ЗАЛ ПРОРОКОВ\n\nВыбери своего Проводника в мире эзотерики."
    try:
        await bot.api.messages.send(
            peer_id=peer_id,
            message=header_text,
            template=json.dumps(carousel_template),
            keyboard=nav_kb.get_json(),
            random_id=0
        )
        if edit_msg_id:
            try:
                await bot.api.messages.edit(
                    peer_id=peer_id,
                    message="Открываю Зал Пророков...",
                    conversation_message_id=edit_msg_id,
                    keyboard=Keyboard(inline=True).get_json()
                )
            except Exception:
                pass
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
        text = (
            "⚙️ НАСТРОЙКИ\n"
            f"✨ Баланс: {balance} Энергии звезд\n\n"
            "Здесь ты можешь управлять своим аккаунтом и Проводником."
        )
        kb_json = get_settings_keyboard()
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
        await message.answer("Для калибровки звездного пути напиши свою ДАТУ рождения (например, 15.04.1990):")
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
            "latest_reading_text": None,
            "latest_reading_data": {},
            "core_profile": ""
        })
        # Удаляем данные из Redis
        from cache import delete_temp_birth_data
        await delete_temp_birth_data(vk_id)
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
            edit_msg_id=edit_msg_id
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
                await update_user(vk_id, {"active_skin": target_skin})
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
                await update_user(vk_id, {
                    "balance": new_balance,
                    "purchased_skins": purchased_skins,
                    "active_skin": target_skin
                })
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
