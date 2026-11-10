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
# Отсортирована по реальным замерам скорости + устойчивости к квотам Free Tier:
# 1) Линейка Flash-Lite (0.3-0.8с, до 1500 RPD) ->
# 2) Рабочие лошадки 2.5 Flash (~1.4-3.4с) и 3.6 Flash (~8.6с) ->
# 3) Бесплатная Gemma 4 (Open-Weights через API) ->
# 4) Тяжелые резервы: 2.5 Pro и 3.8 Flash (в хвосте, т.к. 3.8 Flash на Free Tier
#    generateContent сейчас таймаутит >15с даже с thinkingLevel=LOW).
MODELS = [
    ("models/gemini-3.5-flash-lite", "v1beta"),
    ("models/gemini-3.1-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash", "v1beta"),
    ("models/gemini-3.6-flash", "v1beta"),
    ("models/gemma-4-31b-it", "v1beta"),
    ("models/gemma-4-26b-a4b-it", "v1beta"),
    ("models/gemini-2.5-pro", "v1beta"),
    ("models/gemini-3.8-flash", "v1beta"),
]
