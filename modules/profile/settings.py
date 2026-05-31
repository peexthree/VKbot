import json
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from vkbottle.bot import Message
from modules.bot_init import bot
from database import get_user, update_user, set_user_state, delete_user
from cache import acquire_lock, release_lock
from modules.utils import SKIN_ASSETS, upload_local_photo, get_fsm_step, ghost_edit
from modules.profile.keyboards import (
    get_settings_keyboard, get_change_data_keyboard,
    get_reset_confirm_keyboard
)

async def _send_skins_page(
    vk_id: int,
    peer_id: int,
    purchased_skins: list[str],
    idx: int,
    edit_msg_id: int | None,
):
    styles = {
        "Олеся Ивонченко": "сарказм",
        "Серьезный Аскет": "строгость",
        "Влад Череватов": "дерзость",
        "Виктория Райдес": "властность",
        "Олег Шэпс": "загадочность",
        "Александр Шеппс": "мистицизм",
        "Баба Ванга": "пророчества",
        "Григорий Распутин": "безумие",
        "Магистр": "высшее знание"
    }

    free_skins = ["Олеся Ивонченко", "Серьезный Аскет"]

    skins_to_show = []
    # Добавляем бесплатные скины в начало списка
    skins_to_show.append({
        "name": "Олеся Ивонченко",
        "filename": SKIN_ASSETS["Олеся Ивонченко"],
        "style": styles.get("Олеся Ивонченко", "сарказм")
    })
    skins_to_show.append({
        "name": "Серьезный Аскет",
        "filename": SKIN_ASSETS["Серьезный Аскет"],
        "style": styles.get("Серьезный Аскет", "строгость")
    })

    seen_names = {"olesya", "asket", "Олеся Ивонченко", "Серьезный Аскет"}
    for skin_name, filename in SKIN_ASSETS.items():
        if skin_name in seen_names:
            continue
        skins_to_show.append({
            "name": skin_name,
            "filename": filename,
            "style": styles.get(skin_name, "мистицизм")
        })
        seen_names.add(skin_name)

    total_items = len(skins_to_show)
    if total_items > 0:
        idx = idx % total_items

    skin = skins_to_show[idx]
    skin_name = skin["name"]
    is_owned = skin_name in purchased_skins or skin_name in free_skins

    att = await upload_local_photo(bot.api, skin["filename"], peer_id=vk_id)

    kb = Keyboard(inline=True)

    button_cmd = "set_skin" if is_owned else "buy_skin"
    button_label = "ВЫБРАТЬ" if is_owned else "КУПИТЬ (1500 ✨)"
    kb.add(Callback(button_label, payload={"cmd": button_cmd, "skin": skin_name}), color=KeyboardButtonColor.POSITIVE if is_owned else KeyboardButtonColor.PRIMARY)

    if total_items > 1:
        kb.row()
        kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "skin_page", "idx": idx - 1}), color=KeyboardButtonColor.SECONDARY)
        kb.add(Callback("ВПЕРЕД ➡️", payload={"cmd": "skin_page", "idx": idx + 1}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    kb.add(Callback("⚙️ НАСТРОЙКИ", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.PRIMARY)

    header_text = f"✦ ВЫБОР ПЕРСОНАЖА ({idx + 1}/{total_items}) ✦\n\n👤 Персонаж: {skin_name}\n🎭 Стиль: {skin['style']}\n\nВыберите своего проводника."

    try:
        if edit_msg_id:
            await bot.api.messages.edit(peer_id=peer_id, message=header_text, attachment=att, keyboard=kb.get_json(), conversation_message_id=edit_msg_id)
        else:
            await bot.api.messages.send(peer_id=peer_id, message=header_text, attachment=att, keyboard=kb.get_json(), random_id=0)
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
        free_skins = ["Олеся Ивонченко", "Серьезный Аскет"]
        balance = int(user.get("balance", 0) or 0)

        if action == "set_skin":
            if target_skin in free_skins or target_skin in purchased_skins or target_skin == "olesya":
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
                from modules.profile.views import show_profile_logic
                await show_profile_logic(vk_id, peer_id, message, skip_lock=True, conversation_message_id=conversation_message_id)
            else:
                msg = f"Недостаточно Энергии звезд. Цена: {price}.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} Энергии звезд."
                await ghost_edit(bot.api, peer_id, msg, conversation_message_id=conversation_message_id)
    finally:
        if not skip_lock:
            await release_lock(vk_id)
