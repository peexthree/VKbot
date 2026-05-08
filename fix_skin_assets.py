with open("modules/utils.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('"Григорий Распутин": "r.jpeg"', '"Григорий Распутин": "r.jpeg",\n    "Магистр": "magistr.jpeg"')

with open("modules/utils.py", "w", encoding="utf-8") as f:
    f.write(content)

with open("ai_service.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('"Григорий Распутин": "Ты - цифровой Григорий Распутин. Твой стиль - харизма, мистицизм, пророчества о судьбе, глубокая и магнетическая подача."', '"Григорий Распутин": "Ты - цифровой Григорий Распутин. Твой стиль - харизма, мистицизм, пророчества о судьбе, глубокая и магнетическая подача.",\n    "Магистр": "Ты - Магистр, высшая сущность матрицы. Твой стиль - абсолютное знание, лаконичность, всепоглощающая мудрость."')

with open("ai_service.py", "w", encoding="utf-8") as f:
    f.write(content)

with open("modules/profile.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('"Григорий Распутин": "харизма"', '"Григорий absolutный Распутин": "харизма", "Магистр": "абсолютное знание"')

# Oh wait let's just do it directly.
