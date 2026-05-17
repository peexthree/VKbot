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
    """SaaS Главное меню (inline) - Вертикальное"""
    # Ежедневный бонус при каждом открытии меню
    await check_and_give_daily_bonus(vk_id, user, vk_id)

    kb = Keyboard(inline=True)

    kb.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🔮 ПОСЛАНИЯ ТАРО", payload={"cmd": "services_menu", "filter": "tarot"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("✨ ГЛУБОКИЕ РАЗБОРЫ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()

    # Кнопка Натальной карты (если куплена 'all')
    purchased = user.get("purchased_sections", {}) if user else {}
    has_all = purchased.get("all") or (user and user.get("has_full_chart"))
    if has_all:
        kb.add(Callback("🌙 МОЯ КАРТА СУДЬБЫ", payload={"cmd": "natal_chart_menu"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()

    kb.add(Callback("👤 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)

    return kb.get_json()

def get_profile_inline_keyboard() -> str:
    """Клавиатура личного профиля - Вертикальная (макс 6 рядов)"""
    kb = Keyboard(inline=True)

    kb.add(Callback("📜 МОИ РАЗБОРЫ", payload={"cmd": "history_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("📖 ТАЙНЫЙ ГРИМУАР", payload={"cmd": "profile_action", "action": "grimoire"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🤝 МОЙ КРУГ", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("✨ ЭНЕРГИЯ И ДАРЫ", payload={"cmd": "profile_action", "action": "tariffs"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("🌙 НАСТРОЙКИ", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

    return kb.get_json()

def get_settings_inline_keyboard() -> str:
    """Клавиатура настроек - Вертикальная (макс 6 рядов)"""
    kb = Keyboard(inline=True)
    kb.add(Callback("Изменить данные", payload={"cmd": "profile_action", "action": "change_data"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("Сменить Проводника", payload={"cmd": "profile_action", "action": "change_skin"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("✨ ПУТЕВОДИТЕЛЬ", payload={"cmd": "guide"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("⚙️ ТЕХ. РАЗДЕЛ", payload={"cmd": "profile_action", "action": "advanced_settings"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("👤 НАЗАД В ПРОФИЛЬ", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_advanced_settings_inline_keyboard(vk_id: int) -> str:
    """Клавиатура расширенных настроек и системы"""
    kb = Keyboard(inline=True)
    kb.add(Callback("Отменить подписку", payload={"cmd": "profile_action", "action": "cancel_sub"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("СБРОС АККАУНТА", payload={"cmd": "profile_action", "action": "reset_account"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    if vk_id == ADMIN_ID:
        kb.add(Callback("⚙️ КОНСОЛЬ МАГИСТРА", payload={"cmd": "admin_console"}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    kb.add(Callback("⚙️ НАЗАД В НАСТРОЙКИ", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_skin_inline_keyboard(skin_name: str, is_owned: bool) -> str:
    """Выбор/покупка скина - Вертикальная"""
    kb = Keyboard(inline=True)
    if is_owned:
        kb.add(Callback("ВЫБРАТЬ", payload={"cmd": "set_skin", "skin": skin_name}), color=KeyboardButtonColor.POSITIVE)
    else:
        kb.add(Callback("КУПИТЬ 1500 Энергии", payload={"cmd": "buy_skin", "skin": skin_name}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("Назад в настройки ⚙", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_syndicate_inline_keyboard(is_promo_used: bool) -> str:
    """Синдикат - Вертикальная"""
    kb = Keyboard(inline=True)
    kb.add(Callback("Получить Печать 📜", payload={"cmd": "profile_action", "action": "get_seal"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    if not is_promo_used:
        kb.add(Callback("Ввести Печать ✒", payload={"cmd": "profile_action", "action": "enter_seal"}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    kb.add(Callback("👤 НАЗАД В ПРОФИЛЬ", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_catalog_inline_keyboard(idx: int, total_items: int, item_type: str, button_label: str, button_cmd: str, item_key: str, filter_val: str = None) -> str:
    """Универсальная клавиатура каталога - Вертикальная"""
    kb = Keyboard(inline=True)
    kb.add(Callback(button_label, payload={"cmd": button_cmd, "type": item_type, "key": item_key}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("👤 ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()

    if total_items > 1:
        prev_payload = {"cmd": f"{item_type}_page", "idx": idx - 1}
        next_payload = {"cmd": f"{item_type}_page", "idx": idx + 1}
        if filter_val:
            prev_payload["filter"] = filter_val
            next_payload["filter"] = filter_val

        if idx > 0:
            kb.add(Callback("⬅️ НАЗАД", payload=prev_payload), color=KeyboardButtonColor.SECONDARY)
        if idx < total_items - 1:
            kb.add(Callback("ВПЕРЕД ➡️", payload=next_payload), color=KeyboardButtonColor.SECONDARY)

        if idx > 0 or idx < total_items - 1:
            kb.row()

    kb.add(Callback("🏠 ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_natal_chart_inline_keyboard(purchased: dict) -> str:
    """Клавиатура выбора раздела Натальной карты"""
    kb = Keyboard(inline=True)

    # Показываем только те, что КУПЛЕНЫ и еще НЕ использованы (True в purchased)
    sections = [
        ("sex", "👄 СТРАСТЬ"),
        ("money", "💰 ИЗОБИЛИЕ"),
        ("shadow", "🌘 ТЕНЬ"),
        ("final", "🏁 ПУТЬ"),
    ]

    has_any = False
    for key, label in sections:
        if purchased.get(key):
            kb.add(Callback(label, payload={"cmd": "use_section", "key": key}), color=KeyboardButtonColor.POSITIVE)
            kb.row()
            has_any = True

    if not has_any:
        kb.add(Callback("✨ КУПИТЬ ЕЩЕ РАЗ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()

    kb.add(Callback("🏠 ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_history_inline_keyboard(history: list) -> str:
    """Клавиатура истории разборов (макс 6 рядов)"""
    kb = Keyboard(inline=True)

    # Показываем последние 4 разборов (4 ряда) + 2 ряда навигации = 6 рядов
    for i, item in enumerate(history[-4:][::-1]):
        label = f"📜 {item.get('title', 'Разбор')} ({item.get('date', '')})"
        kb.add(Callback(label[:40], payload={"cmd": "view_history", "idx": i}), color=KeyboardButtonColor.PRIMARY)
        kb.row()

    kb.add(Callback("🏠 ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("👤 ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_guide_main_keyboard() -> str:
    """Главная клавиатура Путеводителя"""
    kb = Keyboard(inline=True)
    kb.add(Callback("✨ ЭНЕРГИЯ И ДАРЫ", payload={"cmd": "guide_energy"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🔮 ГЛУБОКИЕ РАЗБОРЫ", payload={"cmd": "guide_services"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🤝 МОЙ КРУГ", payload={"cmd": "guide_syndicate"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🃏 ГРИМУАР И РАНГИ", payload={"cmd": "guide_grimoire"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("👤 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_guide_sub_keyboard(action_label: str, action_payload: dict) -> str:
    """Клавиатура для подразделов Путеводителя"""
    kb = Keyboard(inline=True)
    kb.add(Callback("⬅️ НАЗАД В ПУТЕВОДИТЕЛЬ", payload={"cmd": "guide"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback(action_label, payload=action_payload), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()
