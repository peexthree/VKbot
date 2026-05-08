import re
with open("modules/profile.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace any lingering "get_json" with proper mock for "set_skin" payload
replacements = [
    ('kb.add(Text("ВЫБРАТЬ", payload=json.dumps({"cmd": "set_skin", "skin": skin_name})), color=KeyboardButtonColor.POSITIVE)', 'kb.add(Callback("ВЫБРАТЬ", payload=json.dumps({"cmd": "set_skin", "skin": skin_name})), color=KeyboardButtonColor.POSITIVE)'),
    ('kb.add(Text("КУПИТЬ 1500 Энергии", payload=json.dumps({"cmd": "buy_skin", "skin": skin_name})), color=KeyboardButtonColor.PRIMARY)', 'kb.add(Callback("КУПИТЬ 1500 Энергии", payload=json.dumps({"cmd": "buy_skin", "skin": skin_name})), color=KeyboardButtonColor.PRIMARY)'),
]
for o, n in replacements:
    content = content.replace(o, n)

with open("modules/profile.py", "w", encoding="utf-8") as f:
    f.write(content)
