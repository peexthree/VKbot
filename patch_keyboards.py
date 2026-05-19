with open('modules/keyboards.py', 'r') as f:
    content = f.read()

# Update main_menu_kb
new_main_menu = """def main_menu_kb(vk_id: int, user: dict | None = None) -> str:
    \"\"\"ГЛАВНОЕ МЕНЮ - единственное место с горизонтальной строкой\"\"\"
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

    return kb.get_json()"""

import re
content = re.sub(
    r'def main_menu_kb\(vk_id: int, user: dict \| None = None\) -> str:.*?return kb\.get_json\(\)',
    new_main_menu,
    content,
    flags=re.DOTALL
)

# Update services_menu_kb
new_services_menu = """def services_menu_kb() -> str:
    \"\"\"Меню Услуг\"\"\"
    return vertical_kb([
        ("🔮 Все услуги", "services_catalog", KeyboardButtonColor.PRIMARY),
        ("❤️ Совместимость", "synastry", KeyboardButtonColor.PRIMARY),
        ("⭐ Подписка / Тарифы", {"cmd": "tariff_page", "idx": 0}, KeyboardButtonColor.POSITIVE),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])"""

content = re.sub(
    r'def services_menu_kb\(\) -> str:.*?\]\)',
    new_services_menu,
    content,
    flags=re.DOTALL
)

# Update profile_menu_kb
new_profile_menu = """def profile_menu_kb() -> str:
    \"\"\"Меню Профиля\"\"\"
    return vertical_kb([
        ("✨ Баланс энергии", "balance", KeyboardButtonColor.PRIMARY),
        ("📜 Мои разборы", "history_menu", KeyboardButtonColor.PRIMARY),
        ("🃏 Гримуар", {"cmd": "profile_action", "action": "grimoire"}, KeyboardButtonColor.PRIMARY),
        ("🔄 Сменить скин", {"cmd": "profile_action", "action": "change_skin"}, KeyboardButtonColor.PRIMARY),
        ("⚙️ Настройки", {"cmd": "profile_action", "action": "settings"}, KeyboardButtonColor.SECONDARY),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])"""

content = re.sub(
    r'def profile_menu_kb\(\) -> str:.*?\]\)',
    new_profile_menu,
    content,
    flags=re.DOTALL
)

# Update settings_menu_kb
new_settings_menu = """def settings_menu_kb(vk_id: int) -> str:
    \"\"\"Меню Настроек\"\"\"
    buttons = [
        ("🔄 Сбросить аккаунт", {"cmd": "profile_action", "action": "reset_account"}, KeyboardButtonColor.SECONDARY),
        ("❌ Отменить подписку", {"cmd": "profile_action", "action": "cancel_sub"}, KeyboardButtonColor.SECONDARY),
        ("📞 Поддержка", "support", KeyboardButtonColor.PRIMARY),
    ]
    if vk_id == ADMIN_ID:
        buttons.append(("🛠️ Админ-консоль", "admin_console", KeyboardButtonColor.SECONDARY))

    buttons.append(("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY))
    return vertical_kb(buttons)"""

content = re.sub(
    r'def settings_menu_kb\(vk_id: int\) -> str:.*?return vertical_kb\(buttons\)',
    new_settings_menu,
    content,
    flags=re.DOTALL
)

with open('modules/keyboards.py', 'w') as f:
    f.write(content)
