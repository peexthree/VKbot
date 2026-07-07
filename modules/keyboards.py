from vkbottle import Callback, Keyboard, KeyboardButtonColor, Text, OpenLink
from modules.utils.consts import ADMIN_ID

def vertical_kb(buttons: list[tuple[str, str | dict, str]], nav_buttons: list[tuple[str, str | dict, str]] = None) -> str:
    """Хелпер для создания клавиатуры с вертикальными основными кнопками и горизонтальными навигационными внизу"""
    kb = Keyboard(inline=True)
    for i, btn in enumerate(buttons):
        label, payload, color = btn
        if isinstance(payload, str):
            payload = {"cmd": payload}
        kb.add(Callback(label, payload=payload), color=color)
        # Добавляем ряд только если это не последняя основная кнопка ИЛИ если дальше будут nav_buttons
        if i < len(buttons) - 1 or nav_buttons:
            kb.row()

    if nav_buttons:
        for btn in nav_buttons:
            label, payload, color = btn
            if isinstance(payload, str):
                payload = {"cmd": payload}
            kb.add(Callback(label, payload=payload), color=color)
            # Навигационные кнопки идут в один (последний) горизонтальный ряд

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
    from datetime import datetime, timezone
    cd_label = "🃏 Карта дня"
    cd_color = KeyboardButtonColor.POSITIVE
    if user:
        purchased = user.get("purchased_sections", {})
        last_used_str = purchased.get("card_of_day_last_used")
        if last_used_str:
            def _parse_iso(s):
                from datetime import datetime as dt
                return dt.fromisoformat(s.replace('Z', '+00:00'))

            last_time = _parse_iso(last_used_str)
            now = datetime.now(timezone.utc)
            diff = now - last_time
            if diff.total_seconds() < 24 * 3600:
                cd_color = KeyboardButtonColor.SECONDARY
                remaining = 24 * 3600 - int(diff.total_seconds())
                hours = remaining // 3600
                minutes = (remaining % 3600) // 60
                cd_label = f"⌛ {hours:02d}:{minutes:02d}"

    kb.add(Callback(cd_label, payload={"cmd": "card_of_day_menu"}), color=cd_color)
    kb.row()

    # Ряд 2
    kb.add(Callback("🔮 Услуги", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()

    # Ряд 3 (Горизонтальный)
    kb.add(Callback("📖 ГРИМУАР", payload={"cmd": "profile_action", "action": "grimoire"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("👥 МОЙ КРУГ", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()

    # Ряд 4
    kb.add(Callback("🎭 Зал пророков", payload={"cmd": "hall_of_prophets"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()

    # Ряд 5
    kb.add(Callback("🧭 Путеводитель", payload={"cmd": "guide"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()

    # Ряд 6 (Последний)
    kb.add(Callback("👤 Профиль", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)

    return kb.get_json()

def services_menu_kb() -> str:
    """Меню Услуг"""
    return vertical_kb([
        ("🔮 Все услуги", "service_page", KeyboardButtonColor.PRIMARY),
        ("❤️ Совместимость", {"cmd": "use_section", "key": "synastry"}, KeyboardButtonColor.PRIMARY),
        ("✨ Хиромантия", {"cmd": "use_section", "key": "palmistry"}, KeyboardButtonColor.POSITIVE),
        ("🌙 Сонник", {"cmd": "dream_interpret_start"}, KeyboardButtonColor.POSITIVE),
        ("⭐ Подписка / Тарифы", {"cmd": "tariff_page", "idx": 0}, KeyboardButtonColor.POSITIVE),
    ], nav_buttons=[
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def profile_menu_kb() -> str:
    """Меню Профиля"""
    return vertical_kb([
        ("✨ Баланс энергии", "balance", KeyboardButtonColor.PRIMARY),
        ("📜 Мои разборы", "history_menu", KeyboardButtonColor.PRIMARY),
        ("🃏 Гримуар", {"cmd": "profile_action", "action": "grimoire"}, KeyboardButtonColor.PRIMARY),
        ("🎭 Зал пророков", {"cmd": "profile_action", "action": "change_skin"}, KeyboardButtonColor.PRIMARY),
        ("⚙️ Настройки", {"cmd": "profile_action", "action": "settings"}, KeyboardButtonColor.SECONDARY),
    ], nav_buttons=[
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def settings_menu_kb(vk_id: int, is_muted: bool = False) -> str:
    """Меню Настроек"""
    sub_label = "🔔 Включить Шепот" if is_muted else "🔕 Отключить Шепот"
    sub_action = "resume_sub" if is_muted else "cancel_sub"

    buttons = [
        ("📝 Изменить данные", {"cmd": "profile_action", "action": "change_data"}, KeyboardButtonColor.PRIMARY),
        ("🔄 Сбросить аккаунт", {"cmd": "profile_action", "action": "reset_account"}, KeyboardButtonColor.SECONDARY),
        (sub_label, {"cmd": "profile_action", "action": sub_action}, KeyboardButtonColor.SECONDARY),
        ("📞 Поддержка", "support", KeyboardButtonColor.PRIMARY),
    ]

    nav_buttons = []
    if vk_id == ADMIN_ID:
        nav_buttons.append(("🛠️ КОНСОЛЬ", "admin_console", KeyboardButtonColor.SECONDARY))

    nav_buttons.append(("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY))
    return vertical_kb(buttons, nav_buttons=nav_buttons)

def after_pdf_kb(section: str, card: str = None) -> str:
    """Клавиатура после генерации PDF"""
    kb = Keyboard(inline=True)
    kb.add(Callback("📜 ПОЛНЫЙ PDF-ОТЧЕТ", payload={"cmd": "gen_pdf", "section": section, "card": card}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    # Ачивка Джека Воробья: засчитываем по факту клика на коллбэк и показываем ссылку
    kb.add(Callback("📤 Поделиться в VK", payload={"cmd": "share_click", "section": section, "card": card}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("⭐️ Оценить прогноз", payload={"cmd": "show_rating", "section": section, "card": card}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def rating_keyboard(section: str, card: str = None) -> str:
    """Клавиатура выбора оценки (1-5)"""
    kb = Keyboard(inline=True)
    for i in range(1, 6):
        kb.add(Callback(str(i), payload={"cmd": "set_rating", "val": i, "section": section, "card": card}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("⬅️ Назад", payload={"cmd": "back_to_forecast", "section": section, "card": card}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def feedback_skip_keyboard() -> str:
    """Клавиатура с кнопкой Пропустить для комментария"""
    kb = Keyboard(inline=True)
    kb.add(Callback("Пропустить", payload={"cmd": "skip_feedback"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def post_pdf_kb(section: str, card: str = None) -> str:
    """Клавиатура ПОСЛЕ того как PDF уже получен"""
    kb = Keyboard(inline=True)
    kb.add(Callback("📤 Поделиться в VK", payload={"cmd": "share_click", "section": section, "card": card}), color=KeyboardButtonColor.PRIMARY)
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

def get_history_inline_keyboard(history: list, destiny_data: dict = None, page: int = 0) -> str:
    """Клавиатура истории разборов с пагинацией"""
    kb = Keyboard(inline=True)

    ITEMS_PER_PAGE = 3
    # История отображается в обратном порядке (новые сверху)
    rev_history = history[::-1]
    total_items = len(rev_history)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total_items > 0 else 1
    page = page % total_pages

    # Сначала Карта Судьбы (только на первой странице)
    if page == 0 and destiny_data:
        from cards_data import get_card_data
        c_data = get_card_data(destiny_data.get("card_id", "0"))
        kb.add(Callback(f"⭐ КАРТА СУДЬБЫ: {c_data.get('name')}", payload={"cmd": "view_history", "idx": -1}), color=KeyboardButtonColor.POSITIVE)
        kb.row()

    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_items = rev_history[start_idx:end_idx]

    for i, item in enumerate(current_items):
        real_idx = start_idx + i
        label = f"📜 {item.get('title', 'Разбор')} ({item.get('date', '')})"
        kb.add(Callback(label[:40], payload={"cmd": "view_history", "idx": real_idx}), color=KeyboardButtonColor.PRIMARY)
        kb.row()

    if total_pages > 1:
        kb.add(Callback("◀️", payload={"cmd": "history_menu", "page": page - 1}), color=KeyboardButtonColor.SECONDARY)
        kb.add(Callback(f"{page + 1}/{total_pages}", payload={"cmd": "history_menu", "page": page}), color=KeyboardButtonColor.SECONDARY)
        kb.add(Callback("▶️", payload={"cmd": "history_menu", "page": page + 1}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_catalog_inline_keyboard(idx: int, total_items: int, item_type: str, button_label: str, button_cmd: str, item_key: str, filter_val: str = None, user: dict = None) -> str:
    kb = Keyboard(inline=True)

    # Кнопка действия (Купить/Получить) - Сначала подтверждение
    # Но для Бесплатной карты дня и пополнений подтверждение не нужно.
    if item_key == "destiny_card" and user:
        purchased = user.get("purchased_sections", {})
        if purchased.get("destiny_card_purchased"):
            kb.add(Callback("👀 ПОСМОТРЕТЬ", payload={"cmd": "destiny_card_info"}), color=KeyboardButtonColor.POSITIVE)
            kb.row()
            kb.add(Callback("🔄 ОБНОВИТЬ (1000 ✨)", payload={"cmd": "confirm_buy", "type": "service", "key": "destiny_card_update"}), color=KeyboardButtonColor.PRIMARY)
        else:
            kb.add(Callback("⭐ КУПИТЬ (1500 ✨)", payload={"cmd": "confirm_buy", "type": "service", "key": "destiny_card"}), color=KeyboardButtonColor.POSITIVE)
    elif item_key == "card_of_day" or button_cmd == "card_of_day" or item_key.startswith("topup_"):
        actual_label = button_label
        actual_color = KeyboardButtonColor.POSITIVE
        if item_key == "card_of_day" and user:
            from datetime import datetime as dt, timezone
            purchased = user.get("purchased_sections", {})
            last_used_str = purchased.get("card_of_day_last_used")
            if last_used_str:
                last_time = dt.fromisoformat(last_used_str.replace('Z', '+00:00'))
                now = dt.now(timezone.utc)
                diff = now - last_time
                if diff.total_seconds() < 24 * 3600:
                    actual_color = KeyboardButtonColor.SECONDARY
                    remaining = 24 * 3600 - int(diff.total_seconds())
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60
                    actual_label = f"⌛ {hours:02d}:{minutes:02d}"

        kb.add(Callback(actual_label, payload={"cmd": button_cmd, "type": item_type, "key": item_key}), color=actual_color)
    else:
        # Для остальных - ведем на экран подтверждения
        kb.add(Callback(button_label, payload={"cmd": "confirm_buy", "type": item_type, "key": item_key}), color=KeyboardButtonColor.POSITIVE)
    kb.row()

    if item_type == "tariff":
        kb.add(OpenLink(link="https://vk.com/@taroanti-oferta", label="📜 ОФЕРТА"))
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

def get_settings_inline_keyboard(vk_id: int = 0, is_muted: bool = False) -> str:
    return settings_menu_kb(vk_id, is_muted=is_muted)

def get_syndicate_inline_keyboard(is_promo_used: bool) -> str:
    # Оставляем старую логику для синдиката, но причесываем
    return vertical_kb([
        ("📜 МОЙ ШИФР", {"cmd": "profile_action", "action": "get_seal"}, KeyboardButtonColor.PRIMARY),
        *([("✒️ ВВЕСТИ ШИФР", {"cmd": "profile_action", "action": "enter_seal"}, KeyboardButtonColor.SECONDARY)] if not is_promo_used else []),
    ], nav_buttons=[
        ("👤 В ПРОФИЛЬ", "profile_menu", KeyboardButtonColor.PRIMARY),
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
    ], nav_buttons=[
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def get_guide_sub_keyboard(action_label: str, action_payload: dict) -> str:
    return vertical_kb([
        (action_label, action_payload, KeyboardButtonColor.POSITIVE),
    ], nav_buttons=[
        ("⬅️ НАЗАД", "guide", KeyboardButtonColor.PRIMARY),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def get_advanced_settings_inline_keyboard(vk_id: int, is_muted: bool = False) -> str:
    """Меню системных настроек"""
    sub_label = "🔔 Включить Шепот" if is_muted else "🔕 Отключить Шепот"
    sub_action = "resume_sub" if is_muted else "cancel_sub"

    buttons = [
        ("🔄 Сбросить аккаунт", {"cmd": "profile_action", "action": "reset_account"}, KeyboardButtonColor.SECONDARY),
        (sub_label, {"cmd": "profile_action", "action": sub_action}, KeyboardButtonColor.SECONDARY),
    ]
    return vertical_kb(buttons, nav_buttons=[
        ("👤 В ПРОФИЛЬ", "profile_menu", KeyboardButtonColor.PRIMARY),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

def get_sections_keyboard(vk_id: int, user: dict) -> str:
    """Старый хелпер, возвращает главное меню"""
    return main_menu_kb(vk_id, user)
