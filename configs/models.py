MODELS = [
    # Живые модели Google Gemini, отсортированы по скорости и стабильности на живом ключе:
    # 3.5-flash-lite (~730мс), 2.5-flash-lite (~300мс), 2.5-flash (~3.4с), 3.5-flash (~7.5с).
    # gemini-flash-latest / 3.8-flash исключены: на generateContent уходят в thinking-таймаут >15с.
    ("models/gemini-3.5-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash-lite", "v1beta"),
    ("models/gemini-2.5-flash", "v1beta"),
    ("models/gemini-3.5-flash", "v1beta"),
    ("models/gemini-3.1-flash-lite", "v1beta"),
]
