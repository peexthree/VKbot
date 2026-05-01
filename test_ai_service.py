import asyncio
from ai_service import generate_text

async def main():
    print(await generate_text("Тестовый запрос: скажи 'Привет мир' без маркдауна."))

asyncio.run(main())
