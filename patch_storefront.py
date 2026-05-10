import re
with open("modules/utils.py", "r") as f:
    content = f.read()
new_func = """async def get_storefront_keyboard(purchased: dict) -> str | None:
    \"\"\"Генерирует резервную инлайн клавиатуру для витрины услуг\"\"\"
    kb = Keyboard(inline=True)
    kb.add(Callback("👄 Сексуальность", payload={"cmd": "buy", "item": "sex"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Callback("💰 Богатство", payload={"cmd": "buy", "item": "money"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("🌘 Тень", payload={"cmd": "buy", "item": "shadow"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Callback("🏁 Путь", payload={"cmd": "buy", "item": "final"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("👨‍❤️‍👨 Синастрия", payload={"cmd": "buy", "item": "synastry"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("❓ Оракул", payload={"cmd": "buy", "item": "oracle"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("👁 Антитаро", payload={"cmd": "buy", "item": "antitaro"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("👑 Архив (Всё)", payload={"cmd": "buy", "item": "all"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Callback("🏠 В главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()"""
content = re.sub(
    r'async def get_storefront_keyboard\(purchased: dict\) -> str \| None:\n\s+# Эта функция больше не используется для основной витрины\n\s+return None',
    new_func,
    content
)
with open("modules/utils.py", "w") as f:
    f.write(content)
