MODELS = [
    # Чистка 2026-11: убрана отключенная Google модель gemini-2.5-flash-lite (возвращала 404).
    # Добавлена рекомендуемая Google gemini-3.5-flash-lite и проверенные быстрые flash-модели.
    ("models/gemini-3.5-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash", "v1beta"),
    ("models/gemini-2.5-flash", "v1"),
    ("models/gemini-3-flash-preview", "v1beta"),
    ("models/gemini-2.0-flash", "v1"),
    ("models/gemini-3-pro-preview", "v1beta"),
]
