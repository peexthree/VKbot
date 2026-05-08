import re

with open("ai_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add a pre-filter at the beginning of generate_text
old_generate = """async def generate_text(prompt: str, json_mode: bool = False, skin: str = "olesya") -> str | None:
    api_keys = await get_gemini_api_keys()
    if not api_keys:
        logger.error("No API keys provided")
        return None"""

new_generate = """STOP_WORDS_18PLUS = [
    "порно", "секс", "эротика", "насилие", "инцест", "педофилия", "убийство",
    "самоубийство", "суицид", "расчлененка", "наркотики", "шлюха", "проститутка",
    "членосос", "пизда", "хуй", "ебать", "трахаться", "порнуха", "извращение", "грязь"
]

async def generate_text(prompt: str, json_mode: bool = False, skin: str = "olesya") -> str | None:
    # Pre-filtering to save tokens and prevent 18+ content execution
    if not json_mode:
        prompt_lower = prompt.lower()
        if any(word in prompt_lower for word in STOP_WORDS_18PLUS):
            return "Матрица отвергает этот запрос. Энергия этого вопроса разрушительна или нарушает баланс. Сформулируй свой вопрос чище."

    api_keys = await get_gemini_api_keys()
    if not api_keys:
        logger.error("No API keys provided")
        return None"""

content = content.replace(old_generate, new_generate)

with open("ai_service.py", "w", encoding="utf-8") as f:
    f.write(content)
