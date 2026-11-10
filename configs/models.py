# Конфигурация актуальных моделей Google Gemini & Gemma 4 (Free Tier + Fallback)
# Проверены живыми POST generateContent запросами через Cloudflare Proxy.

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
# 1) Линейка Flash-Lite (0.3-2.2с, до 1500 RPD, проверено 200 OK) ->
# 2) Быстрые рабочие лошадки 3-flash-preview (~1.4с), 2.5-flash (~1.4-3.4с) ->
# 3) Резерв 3.6-flash (~8.6с с thinkingLevel=LOW) и 3.5-flash (~7.5-8.3с) ->
# 4) Бесплатная Gemma 4 и 3.8-flash в хвосте резерва.
# gemini-2.5-pro исключена: на этом ключе Google отвечает 404 ("no longer available to new users").
MODELS = [
    ("models/gemini-3.5-flash-lite", "v1beta"),
    ("models/gemini-3.1-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash-lite", "v1beta"),
    ("models/gemini-3-flash-preview", "v1beta"),
    ("models/gemini-2.5-flash", "v1beta"),
    ("models/gemini-3.6-flash", "v1beta"),
    ("models/gemini-3.5-flash", "v1beta"),
    ("models/gemma-4-31b-it", "v1beta"),
    ("models/gemma-4-26b-a4b-it", "v1beta"),
    ("models/gemini-3.8-flash", "v1beta"),
]
