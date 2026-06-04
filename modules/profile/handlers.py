import re
from vkbottle.bot import BotLabeler, Message
from modules.states import MyStates
from modules.utils import get_fsm_step

from modules.profile.settings import (
    settings_handler_logic, settings_change_data_logic,
    settings_cancel_subscription_logic,
    settings_reset_account_logic, confirm_reset_account_logic,
    settings_choose_character_logic, process_skin_action_logic
)
from modules.profile.views import (
    show_balance_logic, show_profile_logic,
    god_mode_logic, syndicate_dashboard_logic,
    get_seal_logic, enter_seal_logic,
    cancel_seal_logic, apply_promo_logic,
    show_guide_logic, show_advanced_settings_logic
)
from modules.profile.grimoire import (
    show_grimoire_page, view_card_direct
)
from database import set_user_state

labeler = BotLabeler()

@labeler.message(func=lambda m: m.text and m.text.lower() in ['✦ баланс', 'баланс', '💳 баланс'])
async def show_balance(message: Message):
    await show_balance_logic(message.from_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['✦ настройки ⚙', 'настройки', '⚙ настройки'])
async def settings_handler(
    message: Message = None,
    vk_id: int = None,
    peer_id: int = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    v_id = vk_id or (message.from_id if message else None)
    p_id = peer_id or (message.peer_id if message else None)
    if not v_id or not p_id: return
    await settings_handler_logic(v_id, p_id, message, skip_lock=skip_lock, conversation_message_id=conversation_message_id)

@labeler.message(func=lambda m: m.text and m.text.lower() == "изменить свои данные")
async def settings_change_data(message: Message):
    await settings_change_data_logic(message.from_id, message)

async def is_waiting_for_seal(message: Message) -> bool:
    if not message.text: return False
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_for_seal"

@labeler.message(func=is_waiting_for_seal)
async def process_waiting_seal(message: Message):
    # Если это не попало в apply_promo_handler, значит код неверный
    await apply_promo_logic(message.from_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() == "отменить подписку")
async def settings_cancel_subscription(message: Message):
    await settings_cancel_subscription_logic(message.from_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() == "сброс аккаунта")
async def settings_reset_account(message: Message):
    await settings_reset_account_logic(message.from_id, message)

@labeler.message(state=MyStates.WAITING_RESET_CONFIRM, func=lambda m: m.text and m.text.lower() == "подтвердить сброс")
async def confirm_reset_account(message: Message):
    await confirm_reset_account_logic(message.from_id, message)

@labeler.message(state=MyStates.WAITING_RESET_CONFIRM, func=lambda m: m.text and m.text.lower() == "назад в профиль")
async def cancel_reset_account(message: Message):
    await set_user_state(message.from_id, "")
    await show_profile_logic(message.from_id, message.peer_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() == "назад в профиль")
async def settings_back_to_profile(message: Message):
    await show_profile_logic(message.from_id, message.peer_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() in ["выбрать персонажа", "зал пророков"])
async def settings_choose_character(message: Message = None, vk_id: int = None, peer_id: int = None, skip_lock: bool = False, idx: int = 0, edit_msg_id: int = None):
    v_id = vk_id or (message.from_id if message else None)
    p_id = peer_id or (message.peer_id if message else None)
    if not v_id or not p_id: return
    await settings_choose_character_logic(v_id, p_id, message, skip_lock=skip_lock, idx=idx, edit_msg_id=edit_msg_id)

@labeler.message(func=lambda m: m.payload and "cmd" in m.payload and "skin" in m.payload)
async def process_skin_action(message: Message):
    await process_skin_action_logic(message.from_id, message.peer_id, message)


@labeler.message(func=lambda m: m.text and m.text.lower() in ['🎴 мой гримуар', 'гримуар'])
async def show_grimoire(message: Message):
    await set_user_state(message.from_id, "")
    await show_grimoire_page(message.from_id, message.peer_id, 0)

@labeler.message(func=lambda m: m.text and bool(re.match(r"(?i)^гримуар\s+\d+$", m.text.strip())))
async def view_grimoire_card(message: Message):
    match = re.match(r"(?i)^гримуар\s+(\d+)$", message.text.strip())
    if not match: return
    await view_card_direct(message.from_id, message.peer_id, match.group(1))

@labeler.message(func=lambda m: m.text and m.text.lower() in ['лайн голос'])
async def god_mode_handler(message: Message):
    await god_mode_logic(message.from_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['🕸 синдикат', 'синдикат'])
async def syndicate_dashboard_handler(
    message: Message = None,
    vk_id: int = None,
    peer_id: int = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    v_id = vk_id or (message.from_id if message else None)
    p_id = peer_id or (message.peer_id if message else None)
    if not v_id or not p_id: return
    await syndicate_dashboard_logic(v_id, p_id, message, skip_lock=skip_lock, conversation_message_id=conversation_message_id)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['назад в профиль 👤'])
async def back_to_profile(message: Message):
    await show_profile_logic(message.from_id, message.peer_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['получить печать 📜', 'мой шифр 📜'])
async def get_seal_handler(message: Message):
    await get_seal_logic(message.from_id, message.peer_id)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['ввести печать ✒', 'ввести шифр ✒'])
async def enter_seal_handler(message: Message):
    await enter_seal_logic(message.from_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['отмена'])
async def cancel_seal_handler(message: Message):
    await cancel_seal_logic(message.from_id, message.peer_id, message)

@labeler.message(func=lambda m: m.text and bool(re.match(r"(?i)^([A-Z2-9]{6}|(ПРОМО|ПЕЧАТЬ)-\d+)$", m.text.strip().upper())))
async def apply_promo_handler(message: Message):
    await apply_promo_logic(message.from_id, message)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['✦ путеводитель', 'путеводитель', 'путеводитель', '📖 путеводитель', '📖 путеводитель'])
async def show_guide(
    message: Message = None,
    vk_id: int = None,
    peer_id: int = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    v_id = vk_id or (message.from_id if message else None)
    p_id = peer_id or (message.peer_id if message else None)
    if not v_id or not p_id: return
    await show_guide_logic(v_id, p_id, message, skip_lock=skip_lock, conversation_message_id=conversation_message_id)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['⚙️ система'])
async def show_advanced_settings(
    message: Message = None,
    vk_id: int = None,
    peer_id: int = None,
    skip_lock: bool = False,
    conversation_message_id: int = None
):
    v_id = vk_id or (message.from_id if message else None)
    p_id = peer_id or (message.peer_id if message else None)
    if not v_id or not p_id: return
    await show_advanced_settings_logic(v_id, p_id, message, skip_lock=skip_lock, conversation_message_id=conversation_message_id)
@labeler.message(func=lambda m: m.text and m.text.lower() in ['профиль', 'мой профиль', '✦ мой профиль', '💳 мой профиль', '👤 мой профиль'])
async def show_profile(message: Message):
    """Просто вызывает новый красивый профиль"""
    await show_profile_logic(message.from_id, message.peer_id, message)
