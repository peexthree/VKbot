import os
import asyncio
import aiohttp
from vkbottle import Bot, Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
from vkbottle.bot import Message
from database import add_user, get_balance, decrease_balance
from ai_service import process_image

vk_token = os.environ.get("VK_TOKEN", "")
bot = Bot(token=vk_token)

user_photos = {}

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

    # Process image in a separate thread so it doesn't block the event loop
    prompt_type = message.text
    processed_image_bytes = await asyncio.to_thread(process_image, prompt_type, image_bytes)

    if not processed_image_bytes:
        await message.answer("Произошла ошибка при обработке. Ваша попытка не списана, попробуйте другое фото.")
        return

    try:
        uploader = PhotoMessageUploader(bot.api)
        photo_attachment = await uploader.upload(processed_image_bytes, peer_id=message.peer_id)

        # Only decrease balance after successful processing
        await decrease_balance(vk_id)
        new_balance = balance - 1

        await message.answer(
            f"Готово! Твой новый баланс: {new_balance} генераций.",
            attachment=photo_attachment,
            keyboard=get_keyboard()
        )
    except Exception as e:
        await message.answer(f"Ошибка при загрузке готового фото: {e}")

if __name__ == "__main__":
    bot.run_forever()
