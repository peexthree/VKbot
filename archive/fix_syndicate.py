with open("modules/profile.py", "r", encoding="utf-8") as f:
    content = f.read()

old_text = """    if syndicate_count >= 5:
        rank = "Теневой Кардинал"
    elif syndicate_count >= 1:
        rank = "Вербовщик"
    else:
        rank = "Одиночка"

    text = (
        "🕸 СИНДИКАТ АНТИ-ТАР 🕸\\n\\n"
        f"Твой текущий ранг: {rank}\\n"
        f"Завербовано адептов: {syndicate_count}\\n"
        f"Сгенерировано энергии: {syndicate_energy} ✨\\n\\n"
        "Расширяй свою матрицу. За каждого нового адепта ты получаешь 500 чистой Энергии звезд."
    )"""

new_text = """    progress_text = ""
    if syndicate_count >= 5:
        rank = "Теневой Кардинал"
        progress_text = "Ты достиг вершины синдиката."
    elif syndicate_count >= 1:
        rank = "Вербовщик"
        left = 5 - syndicate_count
        progress_text = f"До статуса Теневой Кардинал осталось {left} адепт(а)."
    else:
        rank = "Одиночка"
        progress_text = "До статуса Вербовщик остался 1 адепт."

    text = (
        "🕸 СИНДИКАТ АНТИ-ТАР 🕸\\n\\n"
        f"Твой текущий ранг: {rank}\\n"
        f"Завербовано адептов: {syndicate_count}\\n"
        f"Сгенерировано энергии: {syndicate_energy} ✨\\n\\n"
        f"{progress_text}\\n\\n"
        "Расширяй свою матрицу. За каждого нового адепта ты получаешь 500 чистой Энергии звезд."
    )"""

content = content.replace(old_text, new_text)

with open("modules/profile.py", "w", encoding="utf-8") as f:
    f.write(content)
