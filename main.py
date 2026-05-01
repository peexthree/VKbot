import ast
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    for attr in ("Num", "Str", "Bytes", "NameConstant", "Ellipsis"):
        if not hasattr(ast, attr):
            setattr(ast, attr, type(attr, (ast.Constant,), {}))

import os
import asyncio

# Глобальный словарь для фото оставляем тут
user_photos = {}

# Легкий обработчик для Render
async def handle_ping(request):
    from aiohttp import web
    return web.Response(text="Bot is alive")

async def main():
    # === 1. ТЯЖЕЛЫЕ ИМПОРТЫ ТОЛЬКО ЗДЕСЬ ===
    import aiohttp
    from aiohttp import web
    from vkbottle import Bot, Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
    from vkbottle.bot import Message
    from database import add_user, get_balance, decrease_balance, init_db
    from ai_service import process_image

    # === 2. ИНИЦИАЛИЗАЦИЯ БОТА И БД ===
    vk_token = os.environ.get("VK_TOKEN", "")
    bot = Bot(token=vk_token)
    
    await init_db()

    # === 3. ЛОГИКА БОТА И ХЕНДЛЕРЫ ===
    def get_keyboard() -> Keyboard:
        keyboard = Keyboard(inline=False)
        keyboard.add(Text("Премиум минимализм"), color=KeyboardButtonColor.PRIMARY)
        keyboard.row()
        keyboard.add(Text("Продающий стиль"), color=KeyboardButtonColor.PRIMARY)
        keyboard.row()
        keyboard.add(Text("Улучшить свет"), color=KeyboardButtonColor.PRIMARY)
        return keyboard.get_json()

    @bot.on.message(text=["Начать", "start", "/start"])
    async def start_handler(message: Message):
        await add_user(message.from_id)
        balance = await get_balance(message.from_id)
        greeting = (
            f"Привет! Я AI-бот для обработки фото.\n"
            f"Твой баланс: {balance} генераций.\n"
            f"Отправь мне фото, а затем выбери стиль!"
        )
        await message.answer(greeting, keyboard=get_keyboard())

    @bot.on.message(func=lambda message: message.attachments and message.attachments[0].photo)
    async def photo_handler(message: Message):
        photo = message.attachments[0].photo
        largest_size = max(photo.sizes, key=lambda size: size.width * size.height)

        user_photos[message.from_id] = largest_size.url
        await message.answer("Фото сохранено! Теперь выбери стиль из меню.", keyboard=get_keyboard())

    @bot.on.message(text=["Премиум минимализм", "Продающий стиль", "Улучшить свет"])
    async def style_handler(message: Message):
        vk_id = message.from_id
        balance = await get_balance(vk_id)

        if balance <= 0:
            await message.answer("У вас закончились генерации. Пожалуйста, пополните баланс.")
            return

        if vk_id not in user_photos:
            await message.answer("Сначала отправьте фото, которое нужно обработать.")
            return

        photo_url = user_photos[vk_id]
        await message.answer("Начинаю обработку... Это может занять несколько секунд.")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as resp:
                    if resp.status == 200:
                        image_bytes = await resp.read()
                    else:
                        await message.answer("Не удалось скачать фото.")
                        return
        except Exception as e:
            await message.answer("Ошибка при скачивании фото.")
            return

        # Обработка фото через ai_service
        prompt_type = message.text
        processed_image_bytes = await process_image(prompt_type, image_bytes)

        if not processed_image_bytes:
            await message.answer("Произошла ошибка при обработке. Ваша попытка не списана, попробуйте другое фото.")
            return

        try:
            uploader = PhotoMessageUploader(bot.api)
            photo_attachment = await uploader.upload(processed_image_bytes, peer_id=message.peer_id)

            # Списываем баланс только в случае успеха
            await decrease_balance(vk_id)
            new_balance = balance - 1

            await message.answer(
                f"Готово! Твой новый баланс: {new_balance} генераций.",
                attachment=photo_attachment,
                keyboard=get_keyboard()
            )
        except Exception as e:
            await message.answer(f"Ошибка при загрузке готового фото: {e}")

    # === 4. ЗАПУСК БОТА И СЕРВЕРА ===
    # Установим флаг, чтобы vkbottle не конфликтовал с текущим loop
    bot.loop_wrapper._running = True
    asyncio.create_task(bot.run_polling())
    
    # Поднимаем веб-сервер для Render
    app = web.Application()
    app.router.add_get('/', handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"Сервер запущен на порту {port}. Бот слушает сообщения...")
    
    # Поддерживаем жизнь процесса
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
