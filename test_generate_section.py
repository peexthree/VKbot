import asyncio
from ai_service import generate_section, init_session, close_session

async def main():
    init_session()
    try:
        res = await generate_section("card_of_day", "15.04.1990", "12:00", "Москва", tags=["кризис-отношений", "выгорание"])
        print(res)
    finally:
        await close_session()

if __name__ == "__main__":
    asyncio.run(main())
