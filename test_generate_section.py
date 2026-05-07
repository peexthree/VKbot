import asyncio
from ai_service import generate_section

async def main():
    res = await generate_section("card_of_day", "15.04.1990", "12:00", "Москва", tags=["кризис-отношений", "выгорание"])
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
