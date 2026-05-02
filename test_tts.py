import asyncio
import aiohttp

async def test_google_tts():
    text = "Проверка теневого режима. Ваша душа темна."
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text}&tl=ru&client=tw-ob"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            print(resp.status)
            data = await resp.read()
            print(len(data))

asyncio.run(test_google_tts())
