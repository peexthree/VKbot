from modules.keyboards import (
    get_profile_inline_keyboard,
    get_settings_inline_keyboard,
    get_skin_inline_keyboard,
    get_syndicate_inline_keyboard
)

# Прокси-функции для сохранения обратной совместимости по именам
def get_profile_keyboard() -> str:

    return get_profile_inline_keyboard()

def get_settings_keyboard() -> str:
    return get_settings_inline_keyboard()

def get_advanced_settings_keyboard(vk_id: int) -> str:
    from modules.keyboards import get_advanced_settings_inline_keyboard
    return get_advanced_settings_inline_keyboard(vk_id)


def get_skin_keyboard(skin_name: str, is_owned: bool) -> str:
    return get_skin_inline_keyboard(skin_name, is_owned)

def get_syndicate_keyboard(is_promo_used: bool) -> str:
    return get_syndicate_inline_keyboard(is_promo_used)

def get_change_data_keyboard() -> str:
    from vkbottle import Keyboard, KeyboardButtonColor, Callback
    kb = Keyboard(inline=True)
    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_reset_confirm_keyboard() -> str:
    from vkbottle import Keyboard, KeyboardButtonColor, Callback
    kb = Keyboard(inline=True)
    kb.add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def get_cancel_seal_keyboard() -> str:
    from vkbottle import Keyboard, KeyboardButtonColor, Callback
    kb = Keyboard(inline=True)
    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()

def _back_to_profile_btn():
    from vkbottle import Callback
    return Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"})
