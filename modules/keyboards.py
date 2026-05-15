from vkbottle import Callback, Keyboard, KeyboardButtonColor, Text
from modules.utils.consts import ADMIN_ID
from modules.utils.logic import check_and_give_daily_bonus

def get_main_reply_keyboard(vk_id: int) -> str:
    """Нижняя статическая клавиатура (reply)"""
    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("Главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)
    if vk_id == ADMIN_ID:
        kb.add(Text("⚙️ КОНСОЛЬ МАГИСТРА", payload={"cmd": "admin_console"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

async def get_main_inline_keyboard(vk_id: int, user: dict | None) -> str:
    """SaaS Главное меню (inline)"""
    # Ежедневный бонус при каждом открытии меню
    await check_and_give_daily_bonus(vk_id, user, vk_id)

    kb = Keyboard(inline=True)
    kb.add(Callback("🔮 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("🛒 УСЛУГИ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("👤 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("📖 ПУТЕВОДИТЕЛЬ", payload={"cmd": "guide"}), color=KeyboardButtonColor.SECONDARY)

    # Динамические купленные разборы
    purchased = user.get("purchased_sections", {}) if user else {}
    has_all = purchased.get("all") or (user and user.get("has_full_chart"))

    sections = [
        ("sex", "👄 СЕКСУАЛЬНОСТЬ", purchased.get("sex") or has_all),
        ("money", "💰 БОГАТСТВО", purchased.get("money") or has_all),
        ("shadow", "🌘 ТЕНЬ", purchased.get("shadow") or has_all),
        ("final", "🏁 ПУТЬ", purchased.get("final") or has_all),
        ("antitaro", "👁 АНТИТАРО", purchased.get("antitaro")),
        ("synastry", "👨‍❤️‍👨 СИНАСТРИЯ", purchased.get("synastry"))
    ]

    active_sections = [s for s in sections if s[2]]
    if active_sections:
        buttons_in_row = 0
        for key, label, _ in active_sections:
            if buttons_in_row == 0:
                kb.row()
            kb.add(Callback(label, payload={"cmd": "use_section", "key": key}), color=KeyboardButtonColor.POSITIVE)
            buttons_in_row += 1
            if buttons_in_row == 2:
                buttons_in_row = 0

    return kb.get_json()

def get_profile_inline_keyboard() -> str:
    """Клавиатура личного профиля"""
    kb = Keyboard(inline=True)
    kb.add(Callback("⚙ Настройка", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("✨ Пополнить", payload={"cmd": "tariff_page", "idx": 3}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("💎 Тарифы", payload={"cmd": "profile_action", "action": "tariffs"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("🕸 Синдикат", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("📖 Гримуар", payload={"cmd": "profile_action", "action": "grimoire"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("🏠 Главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_settings_inline_keyboard() -> str:
    """Клавиатура настроек"""
    kb = Keyboard(inline=True)
    kb.add(Callback("Изменить свои данные", payload={"cmd": "profile_action", "action": "change_data"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("Выбрать персонажа", payload={"cmd": "profile_action", "action": "change_skin"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("Отменить подписку", payload={"cmd": "profile_action", "action": "cancel_sub"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("СБРОС АККАУНТА", payload={"cmd": "profile_action", "action": "reset_account"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_skin_inline_keyboard(skin_name: str, is_owned: bool) -> str:
    """Выбор/покупка скина"""
    kb = Keyboard(inline=True)
    if is_owned:
        kb.add(Callback("ВЫБРАТЬ", payload={"cmd": "set_skin", "skin": skin_name}), color=KeyboardButtonColor.POSITIVE)
    else:
        kb.add(Callback("КУПИТЬ 1500 Энергии", payload={"cmd": "buy_skin", "skin": skin_name}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("Назад в настройки ⚙", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_syndicate_inline_keyboard(is_veteran: bool) -> str:
    """Синдикат"""
    kb = Keyboard(inline=True)
    kb.add(Callback("Получить Печать 📜", payload={"cmd": "profile_action", "action": "get_seal"}), color=KeyboardButtonColor.PRIMARY)
    if not is_veteran:
        kb.add(Callback("Ввести Печать ✒", payload={"cmd": "profile_action", "action": "enter_seal"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_catalog_inline_keyboard(idx: int, total_items: int, item_type: str, button_label: str, button_cmd: str, item_key: str) -> str:
    """Универсальная клавиатура каталога (Услуги/Тарифы)"""
    kb = Keyboard(inline=True)
    kb.add(Callback(button_label, payload={"cmd": button_cmd, "type": item_type, "key": item_key}), color=KeyboardButtonColor.POSITIVE)

    if total_items > 1:
        kb.row()
        if idx > 0:
            kb.add(Callback("⬅️ НАЗАД", payload={"cmd": f"{item_type}_page", "idx": idx - 1}), color=KeyboardButtonColor.SECONDARY)
        if idx < total_items - 1:
            kb.add(Callback("ВПЕРЕД ➡️", payload={"cmd": f"{item_type}_page", "idx": idx + 1}), color=KeyboardButtonColor.SECONDARY)

    kb.row()
    kb.add(Callback("🏠 ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()
