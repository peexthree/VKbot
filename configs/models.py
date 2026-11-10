MODELS = [
    # Живые актуальные модели Google Gemini (проверены по /v1beta/models на живом ключе;
    # v1beta поддерживает system_instruction). Прежние 2.0/1.5 отключены Google (404).
    ("models/gemini-3.5-flash-lite", "v1beta"),
    ("models/gemini-3.5-flash", "v1beta"),
    ("models/gemini-2.5-flash", "v1beta"),
    ("models/gemini-2.5-flash-lite", "v1beta"),
    ("models/gemini-flash-latest", "v1beta"),
]
