import json

from loguru import logger
from vkbottle import (
    Callback,
    Keyboard,
    KeyboardButtonColor,
)
from vkbottle.bot import BotLabeler, Message

from cache import acquire_lock, release_lock
from database import get_user, set_user_state
from modules.bot_init import bot
from modules.states import MyStates
from modules.utils import (
    get_fsm_step,
    upload_local_photo,
    get_storefront_keyboard,
)

labeler = BotLabeler()

@labeler.message(text=["🔮 ГЛУБОКИЕ РАЗБОРЫ", "ГЛУБОКИЕ РАЗБОРЫ", "✦ Услуги", "Услуги", "✦ УСЛУГИ 🛒"])
async def show_services_handler(message: Message):
    logger.info(f"show_services_handler triggered by from_id={message.from_id}")
    await show_services(message.from_id, message.peer_id, 0)


async def _send_catalog_page(
    vk_id: int,
    peer_id: int,
    items: list[dict],
    idx: int,
    edit_msg_id: int | None,
    header_text: str,
    item_type: str, # "service" or "tariff"
):
    total_items = len(items)
    if not items:
        try:
            await bot.api.messages.send(peer_id=peer_id, message="Раздел пуст.", random_id=0)
        except Exception:
            pass
        return

    if idx < 0 or idx >= total_items:
        idx = 0

    item = items[idx]
    att = None
    if item.get("image_name"):
        try:
            att = await upload_local_photo(bot.api, item["image_name"], peer_id=vk_id)
        except Exception as e:
            logger.error(f"Failed to upload photo {item['image_name']}: {str(e)}")

    button_cmd = "buy" if item["key"] != "card_of_day" else "card_of_day"
    button_label = "КУПИТЬ" if item["key"] != "card_of_day" else "ПОЛУЧИТЬ"

    kb = Keyboard(inline=True)
    kb.add(Callback(button_label, payload={"cmd": button_cmd, "type": item_type, "key": item["key"]}), color=KeyboardButtonColor.POSITIVE)

    kb.row()
    if idx > 0:
        kb.add(Callback("⬅️ НАЗАД", payload={"cmd": f"{item_type}_page", "idx": idx - 1}), color=KeyboardButtonColor.SECONDARY)
    if idx < total_items - 1:
        kb.add(Callback("ВПЕРЕД ➡️", payload={"cmd": f"{item_type}_page", "idx": idx + 1}), color=KeyboardButtonColor.SECONDARY)

    kb.row()
    kb.add(Callback("🏠 ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)

    full_text = f"{header_text}\n\n📦 {item['title']}\n📜 {item['desc']}\n\nПозиция: {idx + 1} из {total_items}"

    try:
        if edit_msg_id:
            await bot.api.messages.edit(peer_id=peer_id, message=full_text, attachment=att, keyboard=kb.get_json(), conversation_message_id=edit_msg_id)
        else:
            await bot.api.messages.send(peer_id=peer_id, message=full_text, attachment=att, keyboard=kb.get_json(), random_id=0)
    except Exception as e:
        logger.error(f"Error sending catalog page: {str(e)}")


async def _ensure_user_state(vk_id: int, peer_id: int) -> bool:
    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        try:
            from modules.bot_init import bot
            await bot.api.messages.send(peer_id=peer_id, message="ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.", random_id=0)
        except Exception as e:
            logger.error(f"Ignored Exception: {str(e)}")
        return False
    return True

async def show_services(vk_id: int, peer_id: int, idx: int = 0, edit_msg_id: int = None):

    if not await _ensure_user_state(vk_id, peer_id):
        return

    services = [
        {"key": "sex", "title": "Твоя сексуальная энергия", "desc": "1000 Энергии. Раскроет матрицу страсти.", "image_name": "uslugi/sex.jpg"},
        {"key": "money", "title": "Код твоего богатства", "desc": "900 Энергии. Пробьет финансовый потолок.", "image_name": "uslugi/Money.jpg"},
        {"key": "shadow", "title": "Твои скрытые грани", "desc": "700 Энергии. Раскроет подавленные эмоции.", "image_name": "uslugi/DEMONS.jpg"},
        {"key": "final", "title": "Твой истинный путь", "desc": "1200 Энергии. Вектор развития.", "image_name": "uslugi/WAYLIFE.jpg"},
        {"key": "synastry", "title": "Тайна ваших отношений", "desc": "1500 Энергии. Жесткий разбор совместимости.", "image_name": "uslugi/SINISTRY.jpg"},
        {"key": "oracle", "title": "Вопрос судьбе (Оракул)", "desc": "500 Энергии. Ответ судьбы без воды.", "image_name": "uslugi/QUEST.jpg"},
        {"key": "antitaro", "title": "Антитаро (Разрыв иллюзий)", "desc": "500 Энергии. Разбор иллюзий.", "image_name": "uslugi/ANTITARO.jpg"},
        {"key": "all", "title": "Золотой архив всех откровений", "desc": "3000 Энергии. Полный доступ ко всем тайнам.", "image_name": "uslugi/VIP.jpg"},
        {"key": "card_of_day", "title": "Карта дня", "desc": "Бесплатно. Твоя персональная карта дня.", "image_name": "uslugi/cardofday.jpg"},
    ]

    await _send_catalog_page(
        vk_id=vk_id,
        peer_id=peer_id,
        items=services,
        idx=idx,
        edit_msg_id=edit_msg_id,
        header_text="✦ ВИТРИНА УСЛУГ ✦\nВыберите услугу и нажмите 'КУПИТЬ'.",
        item_type="service"
    )

async def is_waiting_synastry_name(message: Message) -> bool:
    if message.text:
        if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]):
            return False
        if message.text.lower() in ["начать", "start", "/start", "лайн голос", "главное меню", "профиль", "услуги", "гримуар"]:
            return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_synastry_name"

@labeler.message(func=is_waiting_synastry_name)
async def process_synastry_name(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:

        partner_name = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "waiting_synastry_date", "partner_name": partner_name}))
        await message.answer(f"Имя {partner_name} принято. Теперь введите ДАТУ РОЖДЕНИЯ партнера (например, 15.04.1990):")
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_SYNASTRY_DATE)
async def process_synastry_date(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        partner_date = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")

        await set_user_state(vk_id, json.dumps({
            "step": "waiting_synastry_time",
            "partner_name": partner_name,
            "partner_date": partner_date
        }))
        await message.answer(f"Дата {partner_date} принята. Теперь введите ВРЕМЯ РОЖДЕНИЯ партнера (например, 14:30 или 'не знаю'):")
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_SYNASTRY_TIME)
async def process_synastry_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        partner_time = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")
        partner_date = state_dict.get("partner_date", "")

        await set_user_state(vk_id, json.dumps({
            "step": "waiting_synastry_city",
            "partner_name": partner_name,
            "partner_date": partner_date,
            "partner_time": partner_time
        }))
        await message.answer(f"Время {partner_time} принято. Теперь введите ГОРОД РОЖДЕНИЯ партнера (например, Москва или 'не знаю'):")
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_SYNASTRY_CITY)
async def process_synastry_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        partner_city = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")
        partner_date = state_dict.get("partner_date", "")
        partner_time = state_dict.get("partner_time", "")

        partner_full_info = f"{partner_date} {partner_time} {partner_city}"

        await set_user_state(vk_id, json.dumps({
            "step": "global_cut",
            "target_section": "synastry",
            "partner_name": partner_name,
            "partner_date": partner_full_info
        }))

        kb = Keyboard(inline=True)
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
        await message.answer(
            "ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.",
            keyboard=kb.get_json()
        )
    except Exception as e:
        logger.error(f"Ошибка в процессе синастрии: {str(e)}")
    finally:
        await release_lock(vk_id)

@labeler.message(text=["🛰 ТАРИФЫ"])
async def show_tariffs_handler(message: Message):
    await show_tariffs(message.from_id, message.peer_id, 0)

async def show_tariffs(vk_id: int, peer_id: int, idx: int = 0, edit_msg_id: int = None):

    if not await _ensure_user_state(vk_id, peer_id):
        return

    tariffs = [
        {"key": "tariff_1", "title": "Спутник 7 дней", "desc": "990 Энергии. Ежедневные прогнозы на 7 дней.", "image_name": "uslugi/7day.jpg"},
        {"key": "tariff_2", "title": "Оракул 30 дней", "desc": "2900 Энергии. Полный месяц транзитов.", "image_name": "uslugi/30day.jpg"},
        {"key": "tariff_vip", "title": "VIP Архив", "desc": "5900 Энергии. Золотой архив + месяц транзитов.", "image_name": "uslugi/VIPTOP.jpg"},
    ]

    await _send_catalog_page(
        vk_id=vk_id,
        peer_id=peer_id,
        items=tariffs,
        idx=idx,
        edit_msg_id=edit_msg_id,
        header_text="🛰 ТАРИФЫ 🛰\nВыберите тариф и нажмите 'КУПИТЬ'.",
        item_type="tariff"
    )
