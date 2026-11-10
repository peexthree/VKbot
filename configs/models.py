# Конфигурация актуальных моделей Google Gemini & Gemma 4 (Free Tier + Fallback)

# Легкие и быстрые модели с максимальным RPD (до 1500 RPD) для фоновых задач,
# извлечения тегов, парсинга JSON/дат рождения и микро-запросов.
FAST_LITE_MODELS = [
    ("models/gemini-3.1-flash-lite", "v1beta"),
    ("models/gemini-3.5-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash-lite", "v1beta"),
    ("models/gemma-4-26b-a4b-it", "v1beta"),
    ("models/gemma-4-31b-it", "v1beta"),
]

# Основная цепочка для пользовательских ответов, разборов Таро, Оракула и PDF:
# 1) Флагман 3.8 Flash -> 2) Резерв 3.6 / 2.5 Flash ->
# 3) Скоростная линейка Flash-Lite (3.5 / 3.1 / 2.5) ->
# 4) Бесплатная Gemma 4 (Open-Weights) -> 5) Тяжелый резерв 2.5 Pro.
MODELS = [
    ("models/gemini-3.8-flash", "v1beta"),
    ("models/gemini-3.6-flash", "v1beta"),
    ("models/gemini-2.5-flash", "v1beta"),
    ("models/gemini-3.5-flash-lite", "v1beta"),
    ("models/gemini-3.1-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash-lite", "v1beta"),
    ("models/gemma-4-31b-it", "v1beta"),
    ("models/gemma-4-26b-a4b-it", "v1beta"),
    ("models/gemini-2.5-pro", "v1beta"),
]
