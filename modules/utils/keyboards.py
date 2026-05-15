from modules.keyboards import (
    get_main_reply_keyboard,
    get_main_inline_keyboard,
    get_catalog_inline_keyboard
)

def get_dynamic_keyboard(user: dict | None = None) -> str:
    # Заглушка для совместимости с тестами
    from vkbottle import Keyboard, KeyboardButtonColor, Callback
    kb = Keyboard(inline=True)
    kb.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

# Для обратной совместимости
def get_main_keyboard() -> str:
    # Этот метод теперь должен принимать vk_id, но для совместимости с кодом,
    # который его вызывает без аргументов, мы возвращаем дефолтную reply-клавиатуру.
    # В идеале нужно будет обновить все вызовы.
    return get_main_reply_keyboard(0)

async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    return await get_main_inline_keyboard(vk_id, user)

async def get_storefront_keyboard(purchased: dict = None) -> str | None:
    # Это старый метод, который нигде почти не используется или будет заменен каталогом.
    # Но оставим заглушку.
    from vkbottle import Keyboard, KeyboardButtonColor, Callback
    kb = Keyboard(inline=True)
    kb.add(Callback("🏠 В главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
