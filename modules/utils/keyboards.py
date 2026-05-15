from vkbottle import Callback, Keyboard, KeyboardButtonColor, Text
from modules.utils.logic import check_and_give_daily_bonus
from modules.utils.consts import ADMIN_ID

def get_main_keyboard(vk_id: int = 0) -> str:
    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("Главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)
    if vk_id == ADMIN_ID:
        kb.add(Text("Консоль магистра", payload={"cmd": "profile_action", "action": "admin_console"}), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()

def get_dynamic_keyboard(user: dict | None = None) -> str:
    keyboard = Keyboard(inline=True)
    keyboard.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Callback("🔮 ГЛУБОКИЕ РАЗБОРЫ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    keyboard.add(Callback("💳 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Callback("📖 ПУТЕВОДИТЕЛЬ", payload={"cmd": "guide"}), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()

async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    await check_and_give_daily_bonus(vk_id, user, vk_id)
    purchased = user.get("purchased_sections", {}) if user else {}
    has_all = purchased.get("all") or (user and user.get("has_full_chart"))
    kb = Keyboard(inline=True)
    # Группируем по 2 в ряд для экономии места (лимит 10 рядов)
    kb.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("🔮 УСЛУГИ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("💳 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("📖 ПУТЕВОДИТЕЛЬ", payload={"cmd": "guide"}), color=KeyboardButtonColor.SECONDARY)

    # Админку убираем отсюда по просьбе юзера (она теперь в нижней кнопке)

    sections = [
        ("sex", "👄 СЕКСУАЛЬНОСТЬ", purchased.get("sex") or has_all),
        ("money", "💰 БОГАТСТВО", purchased.get("money") or has_all),
        ("shadow", "🌘 ТЕНЬ", purchased.get("shadow") or has_all),
        ("final", "🏁 ПУТЬ", purchased.get("final") or has_all),
        ("antitaro", "👁 АНТИТАРО", purchased.get("antitaro")),
        ("synastry", "👨‍❤️‍👨 СИНАСТРИЯ", purchased.get("synastry"))
    ]
    active_sections = [s for s in sections if s[2]]
    for key, label, _ in active_sections:
        kb.row()
        kb.add(Callback(label, payload={"cmd": "use_section", "key": key}), color=KeyboardButtonColor.POSITIVE)

    return kb.get_json()

async def get_storefront_keyboard(purchased: dict = None) -> str | None:
    if purchased is None:
        purchased = {}
    kb = Keyboard(inline=True)
    kb.add(Callback("👄 Сексуальность", payload={"cmd": "buy", "type": "service", "key": "sex"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("💰 Богатство", payload={"cmd": "buy", "type": "service", "key": "money"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("🌘 Тень", payload={"cmd": "buy", "type": "service", "key": "shadow"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("🏁 Путь", payload={"cmd": "buy", "type": "service", "key": "final"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("👨‍❤️‍👨 Синастрия", payload={"cmd": "buy", "type": "service", "key": "synastry"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("❓ Оракул", payload={"cmd": "buy", "type": "service", "key": "oracle"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("👁 Антитаро", payload={"cmd": "buy", "type": "service", "key": "antitaro"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("👑 Архив (Всё)", payload={"cmd": "buy", "type": "service", "key": "all"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Callback("🏠 В главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
