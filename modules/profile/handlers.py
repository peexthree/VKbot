import re
from vkbottle.bot import BotLabeler, Message
from modules.states import MyStates
from modules.utils import get_fsm_step

from modules.profile.settings import (
    settings_handler_logic, settings_change_data_logic,
    process_change_date_logic, process_change_time_logic,
    process_change_city_logic, settings_cancel_subscription_logic,
    settings_reset_account_logic, confirm_reset_account_logic,
    settings_choose_character_logic, process_skin_action_logic
)
from modules.profile.views import (
    show_balance_logic, show_profile_logic,
    god_mode_logic, syndicate_dashboard_logic,
    get_seal_logic, enter_seal_logic,
    cancel_seal_logic, apply_promo_logic,
    show_guide_logic
)
from modules.profile.grimoire import (
    show_grimoire_page, view_card_direct
)
from database import set_user_state

labeler = BotLabeler()

@labeler.message(text=["✦ Баланс", "Баланс", "💳 БАЛАНС"])
async def show_balance(message: Message):
    await show_balance_logic(message.from_id, message)

@labeler.message(text=["✦ Настройки ⚙", "Настройки", "⚙ НАСТРОЙКИ"])
async def settings_handler(message: Message = None, vk_id: int = None, peer_id: int = None, skip_lock: bool = False):
    v_id = vk_id or (message.from_id if message else None)
    p_id = peer_id or (message.peer_id if message else None)
    if not v_id or not p_id: return
    await settings_handler_logic(v_id, p_id, message, skip_lock=skip_lock)

@labeler.message(text="Изменить свои данные")
async def settings_change_data(message: Message):
    await settings_change_data_logic(message.from_id, message)

async def is_waiting_change_date(message: Message) -> bool:
    if message.text and any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️"]):
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "date"

@labeler.message(func=is_waiting_change_date)
async def process_change_date(message: Message):
    await process_change_date_logic(message.from_id, message)

async def is_waiting_change_time(message: Message) -> bool:
    if message.text and any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️"]):
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "time"

@labeler.message(func=is_waiting_change_time)
async def process_change_time(message: Message):
    await process_change_time_logic(message.from_id, message)

async def is_waiting_change_city(message: Message) -> bool:
    if message.text and any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️"]):
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "city"

@labeler.message(func=is_waiting_change_city)
async def process_change_city(message: Message):
    await process_change_city_logic(message.from_id, message)

@labeler.message(text="Отменить подписку")
async def settings_cancel_subscription(message: Message):
    await settings_cancel_subscription_logic(message.from_id, message)

@labeler.message(text="СБРОС АККАУНТА")
async def settings_reset_account(message: Message):
    await settings_reset_account_logic(message.from_id, message)

@labeler.message(state=MyStates.WAITING_RESET_CONFIRM, text="ПОДТВЕРДИТЬ СБРОС")
async def confirm_reset_account(message: Message):
    await confirm_reset_account_logic(message.from_id, message)

@labeler.message(state=MyStates.WAITING_RESET_CONFIRM, text="Назад в профиль")
async def cancel_reset_account(message: Message):
    await set_user_state(message.from_id, "")
    await show_profile_logic(message.from_id, message.peer_id, message)

@labeler.message(text="Назад в профиль")
async def settings_back_to_profile(message: Message):
    await show_profile_logic(message.from_id, message.peer_id, message)

@labeler.message(text="Выбрать персонажа")
async def settings_choose_character(message: Message = None, vk_id: int = None, peer_id: int = None, skip_lock: bool = False, idx: int = 0, edit_msg_id: int = None):
    v_id = vk_id or (message.from_id if message else None)
    p_id = peer_id or (message.peer_id if message else None)
    if not v_id or not p_id: return
    await settings_choose_character_logic(v_id, p_id, message, skip_lock=skip_lock, idx=idx, edit_msg_id=edit_msg_id)

@labeler.message(func=lambda m: m.payload and "cmd" in m.payload and "skin" in m.payload)
async def process_skin_action(message: Message):
    await process_skin_action_logic(message.from_id, message)


@labeler.message(text=["🎴 МОЙ ГРИМУАР", "Гримуар"])
async def show_grimoire(message: Message):
    await set_user_state(message.from_id, "")
    await show_grimoire_page(message.from_id, message.peer_id, 0)

@labeler.message(func=lambda m: m.text and re.match(r"(?i)^гримуар\s+\d+$", m.text.strip()))
async def view_grimoire_card(message: Message):
    match = re.match(r"(?i)^гримуар\s+(\d+)$", message.text.strip())
    if not match: return
    await view_card_direct(message.from_id, message.peer_id, match.group(1))

@labeler.message(text=["ЛАЙН ГОЛОС"])
async def god_mode_handler(message: Message):
    await god_mode_logic(message.from_id, message)

@labeler.message(text=["Мой Синдикат 🕸", "Мой Синдикат", "Мой синдикат"])
async def syndicate_dashboard_handler(message: Message = None, vk_id: int = None, peer_id: int = None, skip_lock: bool = False):
    v_id = vk_id or (message.from_id if message else None)
    p_id = peer_id or (message.peer_id if message else None)
    if not v_id or not p_id: return
    await syndicate_dashboard_logic(v_id, p_id, message, skip_lock=skip_lock)

@labeler.message(text=["Назад в профиль 👤"])
async def back_to_profile(message: Message):
    await show_profile_logic(message.from_id, message.peer_id, message)

@labeler.message(text=["Получить Печать 📜"])
async def get_seal_handler(message: Message):
    await get_seal_logic(message.from_id, message)

@labeler.message(text=["Ввести Печать ✒"])
async def enter_seal_handler(message: Message):
    await enter_seal_logic(message.from_id, message)

@labeler.message(text=["Отмена"])
async def cancel_seal_handler(message: Message):
    await cancel_seal_logic(message.from_id, message.peer_id, message)

@labeler.message(func=lambda m: m.text and re.match(r"(?i)^(ПРОМО|ПЕЧАТЬ)-\d+$", m.text.strip()))
async def apply_promo_handler(message: Message):
    await apply_promo_logic(message.from_id, message)

@labeler.message(text=["✦ Путеводитель", "путеводитель", "Путеводитель", "📖 ПУТЕВОДИТЕЛЬ", "📖 Путеводитель"])
async def show_guide(message: Message):
    await show_guide_logic(message.from_id, message.peer_id, message)
@labeler.message(text=["Профиль", "Мой профиль", "✦ Мой профиль", "💳 МОЙ ПРОФИЛЬ", "👤 МОЙ ПРОФИЛЬ"])
async def show_profile(message: Message):
    """Просто вызывает новый красивый профиль"""
    await show_profile_logic(message.from_id, message.peer_id, message)
