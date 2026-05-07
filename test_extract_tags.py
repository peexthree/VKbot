import asyncio
from ai_service import extract_tags

async def main():
    text = "Сегодня карты показывают, что у тебя серьезный кризис в отношениях. Ты чувствуешь себя выгоревшей, а финансовый вопрос также стоит очень остро и требует решения."
    tags = await extract_tags(text)
    print(f"Tags extracted: {tags}")

if __name__ == "__main__":
    asyncio.run(main())
