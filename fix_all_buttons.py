# The instruction "Еще хочу чтобы все кнопки работали по callback вместо текста." means
# inline keyboards should use Callback instead of Text.
# We will check `Keyboard(inline=True)` usages.
import os

def replace_in_file(filepath, replacements):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

replacements_profile = [
    ('kb.add(Text("Изменить свои данные")', 'kb.add(Callback("Изменить свои данные", payload={"cmd": "profile_action", "action": "change_data"})'),
    ('kb.add(Text("Выбрать персонажа")', 'kb.add(Callback("Выбрать персонажа", payload={"cmd": "profile_action", "action": "change_skin"})'),
    ('kb.add(Text("Отменить подписку")', 'kb.add(Callback("Отменить подписку", payload={"cmd": "profile_action", "action": "cancel_sub"})'),
    ('kb.add(Text("СБРОС АККАУНТА")', 'kb.add(Callback("СБРОС АККАУНТА", payload={"cmd": "profile_action", "action": "reset_account"})'),
    ('kb.add(Text("Назад в профиль")', 'kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"})'),
    ('kb.add(Text("ПОДТВЕРДИТЬ СБРОС")', 'kb.add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"})'),
    ('kb.add(Text("ВЫБРАТЬ", payload=', 'kb.add(Callback("ВЫБРАТЬ", payload='),
    ('kb.add(Text("КУПИТЬ 1500 Энергии", payload=', 'kb.add(Callback("КУПИТЬ 1500 Энергии", payload='),
    ('kb.add(Text("✦ Настройки ⚙")', 'kb.add(Callback("✦ Настройки ⚙", payload={"cmd": "profile_action", "action": "settings"})'),
    ('kb.add(Text("⚙️ КОНСОЛЬ МАГИСТРА")', 'kb.add(Callback("⚙️ КОНСОЛЬ МАГИСТРА", payload={"cmd": "profile_action", "action": "admin_console"})'),
    ('kb.add(Text("Мой Синдикат 🕸")', 'kb.add(Callback("Мой Синдикат 🕸", payload={"cmd": "profile_action", "action": "syndicate"})'),
    ('kb.add(Text("🎴 МОЙ ГРИМУАР")', 'kb.add(Callback("🎴 МОЙ ГРИМУАР", payload={"cmd": "profile_action", "action": "grimoire"})'),
    ('kb.add(Text("🛰 ТАРИФЫ")', 'kb.add(Callback("🛰 ТАРИФЫ", payload={"cmd": "profile_action", "action": "tariffs"})'),
    ('kb.add(Text("Получить Печать 📜")', 'kb.add(Callback("Получить Печать 📜", payload={"cmd": "profile_action", "action": "get_seal"})'),
    ('kb.add(Text("Ввести Печать ✒")', 'kb.add(Callback("Ввести Печать ✒", payload={"cmd": "profile_action", "action": "enter_seal"})'),
    ('kb.add(Text("Назад в профиль 👤")', 'kb.add(Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"})'),
    ('kb.add(Text("Отмена")', 'kb.add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"})'),
]
replace_in_file("modules/profile.py", replacements_profile)
