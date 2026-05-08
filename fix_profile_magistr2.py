with open("modules/profile.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('"Григорий Распутин": "безумие"\n        }', '"Григорий Распутин": "безумие",\n            "Магистр": "высшее знание"\n        }')

with open("modules/profile.py", "w", encoding="utf-8") as f:
    f.write(content)
