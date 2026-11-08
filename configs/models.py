MODELS = [
    # Чистка 2026-11 (аудит): убраны gemini-3.1-flash-lite-preview (404 на
    # каждом ключе) и модели Gemma (не поддерживают system_instruction -
    # гарантированный 400, т.к. бот кладет скин+инструкцию именно туда).
    # Каждая битая запись удлиняла каждый запрос на лишние 404/400.
    ("models/gemini-2.5-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash-lite", "v1"),
    ("models/gemini-3-flash-preview", "v1beta"),
    ("models/gemini-3-pro-preview", "v1beta"),
    ("models/gemini-2.5-flash", "v1beta"),
    ("models/gemini-2.5-flash", "v1"),
    ("models/gemini-2.0-flash", "v1")
]
