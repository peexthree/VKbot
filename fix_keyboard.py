import re

with open('modules/utils.py', 'r') as f:
    content = f.read()

replacement = '''def get_dynamic_keyboard(user: dict | None) -> str:
    keyboard = Keyboard(inline=False)
    keyboard.add(Text("✦ Услуги"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("🛰 ТАРИФЫ"), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text("✦ Мой профиль"), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text("✦ Главное меню"), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()'''

match = re.search(r'def get_dynamic_keyboard\(user: dict \| None\) -> str:\n.*?return keyboard\.get_json\(\)', content, re.DOTALL)
if match:
    content = content[:match.start()] + replacement + content[match.end():]
    with open('modules/utils.py', 'w') as f:
        f.write(content)
else:
    print("Could not find get_dynamic_keyboard")
