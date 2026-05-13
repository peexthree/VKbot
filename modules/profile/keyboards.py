import json
from vkbottle import Keyboard, KeyboardButtonColor, Callback

def get_settings_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Callback("Изменить свои данные", payload={"cmd": "profile_action", "action": "change_data"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("Выбрать персонажа", payload={"cmd": "profile_action", "action": "change_skin"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("Отменить подписку", payload={"cmd": "profile_action", "action": "cancel_sub"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("СБРОС АККАУНТА", payload={"cmd": "profile_action", "action": "reset_account"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_change_data_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_reset_confirm_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE)
    kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_skin_keyboard(skin_name: str, is_owned: bool) -> str:
    kb = Keyboard(inline=True)
    if is_owned:
        kb.add(Callback("ВЫБРАТЬ", payload=json.dumps({"cmd": "set_skin", "skin": skin_name})), color=KeyboardButtonColor.POSITIVE)
    else:
        kb.add(Callback("КУПИТЬ 1500 Энергии", payload=json.dumps({"cmd": "buy_skin", "skin": skin_name})), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_syndicate_keyboard(is_veteran: bool) -> str:
    kb = Keyboard(inline=True)
    kb.add(Callback("Получить Печать 📜", payload={"cmd": "profile_action", "action": "get_seal"}), color=KeyboardButtonColor.PRIMARY)
    if not is_veteran:
        kb.add(Callback("Ввести Печать ✒", payload={"cmd": "profile_action", "action": "enter_seal"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_cancel_seal_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()
