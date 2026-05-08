import asyncio
from modules.utils import MockMsg

async def main():
    msg = MockMsg(1, 1)
    await msg.answer("Hello")

if __name__ == "__main__":
    asyncio.run(main())
