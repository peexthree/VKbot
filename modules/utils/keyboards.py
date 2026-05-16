
from modules.keyboards import (
    get_main_reply_keyboard,
    get_main_inline_keyboard
)

def get_dynamic_keyboard(user: dict | None = None) -> str:
    # Заглушка для совместимости с тестами
    from vkbottle import Keyboard, KeyboardButtonColor, Callback

    kb = Keyboard(inline=True)
    # Группируем по 2 в ряд для экономии места (лимит 10 рядов)
    kb.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


# Для обратной совместимости
def get_main_keyboard(vk_id: int = 0) -> str:
    """Возвращает основную reply-клавиатуру"""
    return get_main_reply_keyboard(vk_id)

async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    return await get_main_inline_keyboard(vk_id, user)


async def get_storefront_keyboard(purchased: dict = None) -> str | None:
    # Это старый метод, который нигде почти не используется или будет заменен каталогом.
    # Но оставим заглушку.
    from vkbottle import Keyboard, KeyboardButtonColor, Callback
    kb = Keyboard(inline=True)


    kb.add(Callback("🏠 В главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
