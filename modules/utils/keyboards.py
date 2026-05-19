from modules.keyboards import (
    get_main_reply_keyboard,
    main_menu_kb
)

def get_dynamic_keyboard(user: dict | None = None) -> str:
    # Используем новое главное меню
    return main_menu_kb(0, user)

def get_main_keyboard(vk_id: int = 0) -> str:
    """Возвращает основную reply-клавиатуру"""
    return get_main_reply_keyboard(vk_id)

async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    return main_menu_kb(vk_id, user)

async def get_storefront_keyboard(purchased: dict = None) -> str | None:
    from modules.keyboards import services_menu_kb
    return services_menu_kb()
