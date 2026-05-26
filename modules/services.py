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
    ghost_edit,
    get_last_bot_msg,
    set_last_bot_msg,
    delete_bot_message
)

labeler = BotLabeler()

@labeler.message(func=lambda m: m.text and m.text.lower() in ['🔮 глубокие разборы', 'глубокие разборы', '✦ услуги', 'услуги', '✦ услуги 🛒'])
async def show_services_handler(message: Message):
    logger.info(f"show_services_handler triggered by from_id={message.from_id}")
    last_mid = await get_last_bot_msg(message.from_id)
    if last_mid:
        await delete_bot_message(bot.api, message.peer_id, mid=last_mid)
    await show_services(message.from_id, message.peer_id, 0)


async def _send_catalog_page(
    vk_id: int,
    peer_id: int,
    items: list[dict],
    idx: int,
    edit_msg_id: int | None,
    header_text: str,
    item_type: str, # "service" or "tariff"
    filter_val: str = None,
    fallback_att: str = None
):
    total_items = len(items)
    if not items:
        try:
            await bot.api.messages.send(peer_id=peer_id, message="Раздел пуст.", random_id=0)
        except Exception:
            pass
        return

    if total_items > 0:
        idx = idx % total_items

    item = items[idx]
    att = None
    if item.get("image_name"):
        try:
            att = await upload_local_photo(bot.api, item["image_name"], peer_id=vk_id)
        except Exception as e:
            logger.error(f"Failed to upload photo {item['image_name']}: {str(e)}")

    if not att:
        att = fallback_att

    button_cmd = "buy" if item["key"] != "card_of_day" else "card_of_day"
    button_label = "КУПИТЬ" if item["key"] != "card_of_day" else "ПОЛУЧИТЬ"

    from modules.keyboards import get_catalog_inline_keyboard
    user = await get_user(vk_id)
    kb_json = get_catalog_inline_keyboard(
        idx=idx,
        total_items=total_items,
        item_type=item_type,
        button_label=button_label,
        button_cmd=button_cmd,
        item_key=item["key"],
        filter_val=filter_val,
        user=user
    )

    full_text = f"{header_text}\n\n📦 {item['title']}\n📜 {item['desc']}\n\nПозиция: {idx + 1} из {total_items}"

    await ghost_edit(
        bot.api,
        peer_id,
        full_text,
        conversation_message_id=edit_msg_id,
        attachment=att,
        keyboard=kb_json
    )


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

async def show_services(vk_id: int, peer_id: int, idx: int = 0, edit_msg_id: int = None, filter_val: str = None, is_catalog: bool = False, target_key: str = None):
    """Главный экран Услуг с новой клавиатурой"""
    if not await _ensure_user_state(vk_id, peer_id):
        return

    # Если мы зашли в раздел услуг, но не в конкретную пагинацию
    if not is_catalog and not filter_val and not target_key:
        from modules.keyboards import services_menu_kb
        text = "🔮 ВИТРИНА УСЛУГ И ТАЙНЫХ ЗНАНИЙ\n\nВыбери раздел, который откликается твоему запросу."
        header_att = await upload_local_photo(bot.api, "uslugi/main_menu.jpeg", peer_id=vk_id)
        await ghost_edit(bot.api, peer_id, text, keyboard=services_menu_kb(), attachment=header_att, conversation_message_id=edit_msg_id)
        return

    header_att = await upload_local_photo(bot.api, "uslugi/services.jpeg", peer_id=vk_id)

    services = [
        {"key": "synastry", "title": "❤️ Совместимость", "desc": "1500 Энергии. Глубокий анализ ваших отношений по звездам. Узнайте, созданы ли вы друг для друга.", "image_name": "uslugi/SINISTRY.jpeg", "category": "deep"},
        {"key": "sex", "title": "🔥 Страсть", "desc": "1000 Энергии. Погружение в мир твоих чувств и желаний.", "image_name": "uslugi/sex.jpeg", "category": "deep"},
        {"key": "money", "title": "💰 Денежный поток", "desc": "900 Энергии. Раскрой свой путь к финансовой свободе.", "image_name": "uslugi/Money.jpeg", "category": "deep"},
        {"key": "shadow", "title": "👹 Ваши демоны", "desc": "700 Энергии. Встреча с тем, что скрыто в глубине тебя.", "image_name": "uslugi/DEMONS.jpeg", "category": "deep"},
        {"key": "final", "title": "🧭 Ваш путь в жизни", "desc": "1200 Энергии. Главный вектор твоей жизни.", "image_name": "uslugi/WAYLIFE.jpeg", "category": "deep"},
        {"key": "oracle", "title": "🔮 Спроси у звёзд", "desc": "500 Энергии. Ответ на твой самый важный вопрос.", "image_name": "uslugi/QUEST.jpeg", "category": "tarot"},
        {"key": "antitaro", "title": "🃏 Анти-Таро", "desc": "500 Энергии. Взгляд на ситуацию без розовых очков.", "image_name": "uslugi/ANTITARO.jpeg", "category": "tarot"},
        {"key": "all", "title": "👑 VIP", "desc": "3000 Энергии. Полный доступ ко всем твоим тайнам.", "image_name": "uslugi/VIP.jpeg", "category": "deep"},
        {"key": "micro_insight", "title": "🔮 Спроси у звёзд (Микро)", "desc": "100 Энергии. Быстрый совет от твоего Проводника.", "image_name": "uslugi/QUEST.jpeg", "category": "tarot"},
        {"key": "card_of_day", "title": "🎴 Карта дня", "desc": "Бесплатно. Твое личное напутствие на сегодня.", "image_name": "uslugi/cardofday.jpeg", "category": "tarot"},
    ]

    if filter_val:
        services = [s for s in services if s.get("category") == filter_val]

    if target_key:
        for i, s in enumerate(services):
            if s["key"] == target_key:
                idx = i
                break

    # Умные рекомендации на основе тегов
    user = await get_user(vk_id)
    if user and not filter_val:
        tags = user.get("tags", [])
        if tags:
            tags_lower = [t.lower() for t in tags]
            # Если в тегах есть 'отношения' или 'любовь', поднимаем синастрию
            if any(x in " ".join(tags_lower) for x in ["люб", "отнош", "секс", "партнер"]):
                # Перемещаем 'synastry' и 'sex' в начало
                rel_keys = ["synastry", "sex"]
                rel_items = [s for s in services if s["key"] in rel_keys]
                other_items = [s for s in services if s["key"] not in rel_keys]
                services = rel_items + other_items
            # Если есть 'деньги' или 'карьера'
            elif any(x in " ".join(tags_lower) for x in ["ден", "фин", "раб", "бизнес", "карьер"]):
                rel_keys = ["money"]
                rel_items = [s for s in services if s["key"] in rel_keys]
                other_items = [s for s in services if s["key"] not in rel_keys]
                services = rel_items + other_items

    header = "🔮 ПОСЛАНИЯ ТАРО" if filter_val == "tarot" else "✨ КАТАЛОГ УСЛУГ ✨"

    await _send_catalog_page(
        vk_id=vk_id,
        peer_id=peer_id,
        items=services,
        idx=idx,
        edit_msg_id=edit_msg_id,
        header_text=f"{header}\nВыбери то, что откликается твоему сердцу.",
        item_type="service",
        filter_val=filter_val,
        fallback_att=header_att
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
        last_mid = await get_last_bot_msg(vk_id)
        if last_mid:
            await delete_bot_message(bot.api, message.peer_id, mid=last_mid)

        partner_name = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "waiting_synastry_date", "partner_name": partner_name}))
        msg_id = await message.answer(f"Имя {partner_name} согрело колоду ✨ Теперь введи, пожалуйста, дату рождения партнера (например, 15.04.1990):")
        await set_last_bot_msg(vk_id, msg_id)
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_SYNASTRY_DATE)
async def process_synastry_date(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        last_mid = await get_last_bot_msg(vk_id)
        if last_mid:
            await delete_bot_message(bot.api, message.peer_id, mid=last_mid)

        partner_date = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        partner_name = state_dict.get("partner_name", "Партнер")

        await set_user_state(vk_id, json.dumps({
            "step": "waiting_synastry_time",
            "partner_name": partner_name,
            "partner_date": partner_date
        }))
        msg_id = await message.answer(f"Дата {partner_date} принята. Теперь напиши время рождения партнера (например, 14:30 или 'не знаю'):")
        await set_last_bot_msg(vk_id, msg_id)
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_SYNASTRY_TIME)
async def process_synastry_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        last_mid = await get_last_bot_msg(vk_id)
        if last_mid:
            await delete_bot_message(bot.api, message.peer_id, mid=last_mid)

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
        msg_id = await message.answer(f"Время {partner_time} принято. И последнее — в какой городе родился партнер (например, Москва или 'не знаю')?")
        await set_last_bot_msg(vk_id, msg_id)
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_SYNASTRY_CITY)
async def process_synastry_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        last_mid = await get_last_bot_msg(vk_id)
        if last_mid:
            await delete_bot_message(bot.api, message.peer_id, mid=last_mid)

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
        msg_id = await message.answer(
            "✨ ШАГ 2 ИЗ 3: НАСТРОЙКА ✨\nПрикоснись к колоде, чтобы настроиться на вашу связь.",
            keyboard=kb.get_json()
        )
        await set_last_bot_msg(vk_id, msg_id)
    except Exception as e:
        logger.error(f"Ошибка в процессе синастрии: {str(e)}")
    finally:
        await release_lock(vk_id)

@labeler.message(func=lambda m: m.text and m.text.lower() in ['🛰 тарифы', '💳 пополнить'])
async def show_tariffs_handler(message: Message):
    last_mid = await get_last_bot_msg(message.from_id)
    if last_mid:
        await delete_bot_message(bot.api, message.peer_id, mid=last_mid)
    await show_tariffs(message.from_id, message.peer_id, 0)

async def show_tariffs(vk_id: int, peer_id: int, idx: int = 0, edit_msg_id: int = None):

    if not await _ensure_user_state(vk_id, peer_id):
        return

    user = await get_user(vk_id)
    balance = int(user.get("balance", 0) or 0)

    header_att = await upload_local_photo(bot.api, "uslugi/tariffs.jpeg", peer_id=vk_id)

    tariffs = [
        {"key": "tariff_1", "title": "🛰 Спутник 7 дней", "desc": "990 Энергии. Твое ежедневное напутствие на неделю.", "image_name": "uslugi/7day.jpeg"},
        {"key": "tariff_2", "title": "🔮 Оракул 30 дней", "desc": "2900 Энергии. Выгода 400% — Хит! Целый месяц под защитой звезд.", "image_name": "uslugi/30day.jpeg"},
        {"key": "tariff_vip", "title": "🗝 VIP Архив", "desc": "5900 Энергии. Вечный доступ к мудрости + месяц прогнозов.", "image_name": "uslugi/VIPTOP.jpeg"},
        {"key": "topup_5000", "title": "✨ Пакет 5000 Энергии", "desc": "400 руб. Выгодный старт для глубокого погружения.", "image_name": "uslugi/tariffs.jpeg"},
        {"key": "topup_10000", "title": "✨ Пакет 10000 Энергии", "desc": "750 руб. Оптимальный выбор для истинных искателей.", "image_name": "uslugi/tariffs.jpeg"},
        {"key": "topup_50000", "title": "👑 VIP Пакет 50000 Энергии", "desc": "3500 руб. Максимальная выгода и безграничные возможности.", "image_name": "uslugi/VIP.jpeg"},
    ]

    await _send_catalog_page(
        vk_id=vk_id,
        peer_id=peer_id,
        items=tariffs,
        idx=idx,
        edit_msg_id=edit_msg_id,
        header_text=f"✨ ДАРЫ И ЭНЕРГИЯ ✨\nТвой баланс: {balance} ✨\n\nВыбери подходящий объем энергии для своего пути.",
        item_type="tariff",
        fallback_att=header_att
    )
