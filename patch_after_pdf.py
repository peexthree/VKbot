import re
with open('modules/keyboards.py', 'r') as f:
    content = f.read()

new_after_pdf_kb = """def after_pdf_kb(section: str, card: str = None) -> str:
    \"\"\"Клавиатура после генерации PDF\"\"\"
    kb = Keyboard(inline=True)
    kb.add(Callback("📜 ПОЛНЫЙ PDF-ОТЧЕТ", payload={"cmd": "gen_pdf", "section": section, "card": card}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("📤 Поделиться в VK", payload={"cmd": "share_pdf", "section": section}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()"""

content = re.sub(
    r'def after_pdf_kb\(section: str, card: str = None\) -> str:.*?return kb\.get_json\(\)',
    new_after_pdf_kb,
    content,
    flags=re.DOTALL
)

with open('modules/keyboards.py', 'w') as f:
    f.write(content)
