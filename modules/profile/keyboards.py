from vkbottle import Keyboard, KeyboardButtonColor, Callback


def get_profile_keyboard() -> str:
    """Главная клавиатура профиля (Настройки, Тарифы, Гримуар, Синдикат)"""
    kb = Keyboard(inline=True, one_time=False)
    kb.add(Callback("Настройка ⚙", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("Тарифы 💎", payload={"cmd": "profile_action", "action": "tariffs"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("Гримуар 📖", payload={"cmd": "profile_action", "action": "grimoire"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("Мой Синдикат 🕸", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("🔮 УСЛУГИ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("📖 Путеводитель", payload={"cmd": "profile_action", "action": "guide"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("Главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def _back_to_profile_btn() -> Callback:
    """Вспомогательная кнопка «Назад в профиль» (используется везде)"""
    return Callback(
        "Назад в профиль 👤",
        payload={"cmd": "profile_action", "action": "back_to_profile"},
        color=KeyboardButtonColor.PRIMARY,
    )


def get_settings_keyboard() -> str:
    """Клавиатура в настройках профиля"""
    kb = Keyboard(inline=True, one_time=False)
    kb.add(Callback("Изменить свои данные", payload={"cmd": "profile_action", "action": "change_data"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("Выбрать персонажа", payload={"cmd": "profile_action", "action": "change_skin"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("Отменить подписку", payload={"cmd": "profile_action", "action": "cancel_sub"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("СБРОС АККАУНТА", payload={"cmd": "profile_action", "action": "reset_account"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(_back_to_profile_btn())
    return kb.get_json()


def get_change_data_keyboard() -> str:
    """Клавиатура при изменении данных"""
    kb = Keyboard(inline=True, one_time=False)
    kb.add(_back_to_profile_btn())
    return kb.get_json()


def get_reset_confirm_keyboard() -> str:
    """Клавиатура подтверждения сброса аккаунта"""
    kb = Keyboard(inline=True, one_time=False)
    kb.add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(_back_to_profile_btn())
    return kb.get_json()


def get_skin_keyboard(skin_name: str, is_owned: bool) -> str:
    """Клавиатура выбора/покупки скина"""
    kb = Keyboard(inline=True, one_time=False)
    if is_owned:
        kb.add(
            Callback("ВЫБРАТЬ", payload={"cmd": "set_skin", "skin": skin_name}),
            color=KeyboardButtonColor.POSITIVE,
        )
    else:
        kb.add(
            Callback("КУПИТЬ 1500 Энергии", payload={"cmd": "buy_skin", "skin": skin_name}),
            color=KeyboardButtonColor.PRIMARY,
        )
    return kb.get_json()


def get_syndicate_keyboard(is_veteran: bool) -> str:
    """Клавиатура Синдиката"""
    kb = Keyboard(inline=True, one_time=False)
    kb.add(Callback("Получить Печать 📜", payload={"cmd": "profile_action", "action": "get_seal"}), color=KeyboardButtonColor.PRIMARY)
    if not is_veteran:
        kb.add(Callback("Ввести Печать ✒", payload={"cmd": "profile_action", "action": "enter_seal"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(_back_to_profile_btn())
    return kb.get_json()


def get_cancel_seal_keyboard() -> str:
    """Клавиатура отмены ввода Печати"""
    kb = Keyboard(inline=True, one_time=False)
    kb.add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()
