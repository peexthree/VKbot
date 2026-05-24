from vkbottle import Callback, Keyboard, KeyboardButtonColor, Text
from modules.utils.consts import ADMIN_ID

def vertical_kb(buttons: list[tuple[str, str | dict, str]]) -> str:
    """Хелпер для создания строго вертикальной клавиатуры (1 кнопка в ряду)"""
    kb = Keyboard(inline=True)
    for i, btn in enumerate(buttons):
        label, payload, color = btn
        # Превращаем строку payload в словарь если нужно
        if isinstance(payload, str):
            payload = {"cmd": payload}
        kb.add(Callback(label, payload=payload), color=color)
        if i < len(buttons) - 1:
            kb.row()
    return kb.get_json()

def get_main_reply_keyboard(vk_id: int) -> str:
    """Нижняя статическая клавиатура (reply)"""
    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("🏠 ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)
    if vk_id == ADMIN_ID:
        kb.add(Text("⚙️ КОНСОЛЬ", payload={"cmd": "admin_console"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def main_menu_kb(vk_id: int, user: dict | None = None) -> str:
    """ГЛАВНОЕ МЕНЮ - единственное место с горизонтальной строкой"""
    kb = Keyboard(inline=True)

    # Ряд 1
    kb.add(Callback("🃏 Карта дня", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()

    # Ряд 2
    kb.add(Callback("🔮 Услуги", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()

    # Ряд 3 (Горизонтальный)
    kb.add(Callback("📖 ГРИМУАР", payload={"cmd": "profile_action", "action": "grimoire"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("👥 МОЙ КРУГ", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()

    # Ряд 4
    kb.add(Callback("🧭 Путеводитель", payload={"cmd": "guide"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()

    # Ряд 5 - Карта судьбы
    kb.add(Callback("⭐ Моя карта судьбы", payload={"cmd": "destiny_card_info"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()

    # Ряд 6
    kb.add(Callback("👤 Профиль", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)

    return kb.get_json()

def services_menu_kb() -> str:
    """Меню Услуг"""
    return vertical_kb([
        ("🔮 Все услуги", "service_page", KeyboardButtonColor.PRIMARY),
        ("❤️ Совместимость", {"cmd": "use_section", "key": "synastry"}, KeyboardButtonColor.PRIMARY),
        ("⭐ Подписка / Тарифы", {"cmd": "tariff_page", "idx": 0}, KeyboardButtonColor.POSITIVE),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def profile_menu_kb() -> str:
    """Меню Профиля"""
    return vertical_kb([
        ("✨ Баланс энергии", "balance", KeyboardButtonColor.PRIMARY),
        ("📜 Мои разборы", "history_menu", KeyboardButtonColor.PRIMARY),
        ("🃏 Гримуар", {"cmd": "profile_action", "action": "grimoire"}, KeyboardButtonColor.PRIMARY),
        ("🔄 Сменить скин", {"cmd": "profile_action", "action": "change_skin"}, KeyboardButtonColor.PRIMARY),
        ("⚙️ Настройки", {"cmd": "profile_action", "action": "settings"}, KeyboardButtonColor.SECONDARY),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def settings_menu_kb(vk_id: int) -> str:
    """Меню Настроек"""
    buttons = [
        ("🔄 Сбросить аккаунт", {"cmd": "profile_action", "action": "reset_account"}, KeyboardButtonColor.SECONDARY),
        ("❌ Отменить подписку", {"cmd": "profile_action", "action": "cancel_sub"}, KeyboardButtonColor.SECONDARY),
        ("📞 Поддержка", "support", KeyboardButtonColor.PRIMARY),
    ]
    if vk_id == ADMIN_ID:
        buttons.append(("🛠️ Админ-консоль", "admin_console", KeyboardButtonColor.SECONDARY))

    buttons.append(("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY))
    return vertical_kb(buttons)

def after_pdf_kb(section: str, card: str = None) -> str:
    """Клавиатура после генерации PDF"""
    kb = Keyboard(inline=True)
    kb.add(Callback("📜 ПОЛНЫЙ PDF-ОТЧЕТ", payload={"cmd": "gen_pdf", "section": section, "card": card}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("📤 Поделиться в VK", payload={"cmd": "share_pdf", "section": section}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def confirmation_kb(action_payload: dict, cost: int) -> str:
    """Клавиатура подтверждения покупки"""
    kb = Keyboard(inline=True)
    kb.add(Callback(f"✅ ДА, КУПИТЬ ({cost} ✨)", payload=action_payload), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("❌ ОТМЕНА", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()

# --- Остальные клавиатуры (совместимость) ---

def get_history_inline_keyboard(history: list, destiny_data: dict = None) -> str:
    """Клавиатура истории разборов (Гримуар)"""
    kb = Keyboard(inline=True)

    # Сначала Карта Судьбы (если есть)
    if destiny_data:
        from cards_data import get_card_data
        c_data = get_card_data(destiny_data.get("card_id", "0"))
        kb.add(Callback(f"⭐ КАРТА СУДЬБЫ: {c_data.get('name')}", payload={"cmd": "view_history", "idx": -1}), color=KeyboardButtonColor.POSITIVE)
        kb.row()

    # Показываем последние 4 разбора
    for i, item in enumerate(history[-4:][::-1]):
        label = f"📜 {item.get('title', 'Разбор')} ({item.get('date', '')})"
        kb.add(Callback(label[:40], payload={"cmd": "view_history", "idx": i}), color=KeyboardButtonColor.PRIMARY)
        kb.row()

    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_catalog_inline_keyboard(idx: int, total_items: int, item_type: str, button_label: str, button_cmd: str, item_key: str, filter_val: str = None) -> str:
    kb = Keyboard(inline=True)

    # Кнопка действия (Купить/Получить) - Сначала подтверждение
    # Но для Бесплатной карты дня подтверждение не нужно.
    if item_key == "card_of_day" or button_cmd == "card_of_day":
        kb.add(Callback(button_label, payload={"cmd": button_cmd, "type": item_type, "key": item_key}), color=KeyboardButtonColor.POSITIVE)
    else:
        # Для остальных - ведем на экран подтверждения
        kb.add(Callback(button_label, payload={"cmd": "confirm_buy", "type": item_type, "key": item_key}), color=KeyboardButtonColor.POSITIVE)
    kb.row()

    if item_type == "tariff":
        kb.add(Callback("📜 ОФЕРТА", payload={"cmd": "show_offer"}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

    if total_items > 1:
        prev_payload = {"cmd": f"{item_type}_page", "idx": idx - 1}
        next_payload = {"cmd": f"{item_type}_page", "idx": idx + 1}
        if filter_val:
            prev_payload["filter"] = filter_val
            next_payload["filter"] = filter_val

        kb.add(Callback("⬅️ НАЗАД", payload=prev_payload), color=KeyboardButtonColor.SECONDARY)
        kb.add(Callback("ВПЕРЕД ➡️", payload=next_payload), color=KeyboardButtonColor.SECONDARY)
        kb.row()

    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

# Заглушки для старых функций (для плавной миграции)
async def get_main_inline_keyboard(vk_id: int, user: dict | None) -> str:
    return main_menu_kb(vk_id, user)

def get_profile_inline_keyboard() -> str:
    return profile_menu_kb()

def get_settings_inline_keyboard(vk_id: int = 0) -> str:
    return settings_menu_kb(vk_id)

def get_syndicate_inline_keyboard(is_promo_used: bool) -> str:
    # Оставляем старую логику для синдиката, но причесываем
    return vertical_kb([
        ("📜 ПОЛУЧИТЬ ПЕЧАТЬ", {"cmd": "profile_action", "action": "get_seal"}, KeyboardButtonColor.PRIMARY),
        *([("✒️ ВВЕСТИ ПЕЧАТЬ", {"cmd": "profile_action", "action": "enter_seal"}, KeyboardButtonColor.SECONDARY)] if not is_promo_used else []),
        ("👤 В ПРОФИЛЬ", {"cmd": "profile_menu"}, KeyboardButtonColor.PRIMARY),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def get_skin_inline_keyboard(skin_name: str, is_owned: bool) -> str:
    if is_owned:
        return vertical_kb([
            ("✅ ВЫБРАТЬ", {"cmd": "set_skin", "skin": skin_name}, KeyboardButtonColor.POSITIVE),
            ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
        ])
    else:
        return vertical_kb([
            ("💎 КУПИТЬ (1500 ✨)", {"cmd": "confirm_buy", "type": "skin", "key": skin_name}, KeyboardButtonColor.PRIMARY),
            ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
        ])

def get_guide_main_keyboard() -> str:
    return vertical_kb([
        ("✨ ЭНЕРГИЯ И ДАРЫ", "guide_energy", KeyboardButtonColor.PRIMARY),
        ("🔮 ГЛУБОКИЕ РАЗБОРЫ", "guide_services", KeyboardButtonColor.PRIMARY),
        ("🤝 МОЙ КРУГ", "guide_syndicate", KeyboardButtonColor.PRIMARY),
        ("🃏 ГРИМУАР И РАНГИ", "guide_grimoire", KeyboardButtonColor.PRIMARY),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def get_guide_sub_keyboard(action_label: str, action_payload: dict) -> str:
    return vertical_kb([
        ("⬅️ НАЗАД", "guide", KeyboardButtonColor.PRIMARY),
        (action_label, action_payload, KeyboardButtonColor.POSITIVE),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def get_advanced_settings_inline_keyboard(vk_id: int) -> str:
    """Меню системных настроек"""
    buttons = [
        ("🔄 Сбросить аккаунт", {"cmd": "profile_action", "action": "reset_account"}, KeyboardButtonColor.SECONDARY),
        ("❌ Отменить подписку", {"cmd": "profile_action", "action": "cancel_sub"}, KeyboardButtonColor.SECONDARY),
        ("👤 В ПРОФИЛЬ", "profile_menu", KeyboardButtonColor.PRIMARY),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ]
    return vertical_kb(buttons)

def get_sections_keyboard(vk_id: int, user: dict) -> str:
    """Старый хелпер, возвращает главное меню"""
    return main_menu_kb(vk_id, user)
