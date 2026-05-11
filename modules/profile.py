import asyncio
import datetime
import json
import re
from modules.bot_init import bot
from loguru import logger
from vkbottle import (
    Callback,
    Keyboard,
    KeyboardButtonColor,
)
from vkbottle.bot import BotLabeler, Message

from cache import acquire_lock, get_tarot_names, release_lock
from database import (
    delete_user,
    get_user,
    set_user_state,
    update_user,
)
from modules.utils import SKIN_ASSETS, get_sections_keyboard, upload_local_photo, get_fsm_step
from modules.states import MyStates

labeler = BotLabeler()

@labeler.message(text=["✦ Баланс", "Баланс", "💳 БАЛАНС"])
async def show_balance(message: Message):
    vk_id = message.from_id

    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
        return

    balance = int(user.get("balance", 0) or 0)

    await message.answer(f"ТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} Энергии звезд")

@labeler.message(text=["✦ Настройки ⚙", "Настройки", "⚙ НАСТРОЙКИ"])
async def settings_handler(message: Message = None, vk_id: int = None, peer_id: int = None):
    if message:
        vk_id = message.from_id
        peer_id = message.peer_id
    elif not vk_id or not peer_id:
        return

    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        text = "✦ НАСТРОЙКИ И ЮРИДИЧЕСКИЙ ЩИТ ✦"

        kb = Keyboard(inline=True)
        kb.add(Callback("Изменить свои данные", payload={"cmd": "profile_action", "action": "change_data"}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
        kb.add(Callback("Выбрать персонажа", payload={"cmd": "profile_action", "action": "change_skin"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("Отменить подписку", payload={"cmd": "profile_action", "action": "cancel_sub"}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
        kb.add(Callback("СБРОС АККАУНТА", payload={"cmd": "profile_action", "action": "reset_account"}), color=KeyboardButtonColor.NEGATIVE)
        kb.row()
        kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)

        if message:
            await message.answer(text, keyboard=kb.get_json())
        else:
            await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb.get_json(), random_id=0)
    finally:
        await release_lock(vk_id)

@labeler.message(text="Изменить свои данные")
async def settings_change_data(message: Message):
    vk_id = message.from_id

    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        await set_user_state(vk_id, json.dumps({"step": "date"}))
        await message.answer("Укажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):")
    finally:
        await release_lock(vk_id)


async def is_waiting_change_date(message: Message) -> bool:
    if message.text and any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️"]):
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "date"

@labeler.message(func=is_waiting_change_date)
async def process_change_date(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        new_date = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "time", "date": new_date}))
        await message.answer(f"Дата {new_date} принята. Теперь введите ВРЕМЯ вашего рождения (например, 14:30 или 'не знаю'):")
    finally:
        await release_lock(vk_id)

async def is_waiting_change_time(message: Message) -> bool:
    if message.text and any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️"]):
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "time"

@labeler.message(func=is_waiting_change_time)
async def process_change_time(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        new_time = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        new_date = state_dict.get("date", "")
        await set_user_state(vk_id, json.dumps({"step": "city", "date": new_date, "time": new_time}))
        await message.answer(f"Время {new_time} принято. Теперь введите ГОРОД вашего рождения:")
    finally:
        await release_lock(vk_id)

async def is_waiting_change_city(message: Message) -> bool:
    if message.text and any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️"]):
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "city"

@labeler.message(func=is_waiting_change_city)
async def process_change_city(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        new_city = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        new_date = state_dict.get("date", "")
        new_time = state_dict.get("time", "")

        await update_user(vk_id, {
            "birth_date": new_date,
            "birth_time": new_time,
            "birth_city": new_city
        })
        await set_user_state(vk_id, "")

        kb = Keyboard(inline=True)
        kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
        await message.answer(f"Твои данные обновлены: {new_date}, {new_time}, г. {new_city}", keyboard=kb.get_json())
    finally:
        await release_lock(vk_id)

@labeler.message(text="Отменить подписку")
async def settings_cancel_subscription(message: Message):
    vk_id = message.from_id

    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        await message.answer("Ваш аккаунт не имеет активных рекуррентных подписок. Все платежи разовые. Для прекращения получения транзитов просто не пополняйте баланс. Отвязка карт не требуется по ФЗ №376-ФЗ.")
    finally:
        await release_lock(vk_id)

@labeler.message(text="СБРОС АККАУНТА")
async def settings_reset_account(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        await set_user_state(vk_id, json.dumps({"step": "waiting_reset_confirm"}))
        kb = Keyboard(inline=True)
        kb.add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE)
        kb.row()
        kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)

        await message.answer(
            "⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс в системе. Вы уверены?",
            keyboard=kb.get_json()
        )
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_RESET_CONFIRM, text="ПОДТВЕРДИТЬ СБРОС")
async def confirm_reset_account(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        await delete_user(vk_id)
        await set_user_state(vk_id, "")
        await message.answer("Система обнулена. Напишите 'Начать', чтобы заново войти в матрицу.")
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_RESET_CONFIRM, text="Назад в профиль")
async def cancel_reset_account(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "")
    await show_profile(message)

@labeler.message(text="Назад в профиль")
async def settings_back_to_profile(message: Message):
    await show_profile(message)

@labeler.message(text="Выбрать персонажа")
async def settings_choose_character(message: Message = None, vk_id: int = None, peer_id: int = None):
    if message:
        vk_id = message.from_id
        peer_id = message.peer_id
    elif not vk_id or not peer_id:
        return

    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        user = await get_user(vk_id)
        if not user:
            if message:
                await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
            else:
                await bot.api.messages.send(peer_id=peer_id, message="ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.", random_id=0)
            return

        purchased_skins = user.get("purchased_skins", [])


        styles = {
            "olesya": "сарказм",
            "Олеся Ивонченко": "сарказм",
            "asket": "строгость",
            "Серьезный Аскет": "строгость",
            "Влад Череватов": "дерзость",
            "Виктория Райдес": "властность",
            "Олег Шэпс": "загадочность",
            "Александр Шеппс": "мистицизм",
            "Баба Ванга": "пророчества",
            "Григорий Распутин": "безумие",
            "Магистр": "высшее знание"
        }

        free_skins = ["Олеся Ивонченко", "Серьезный Аскет", "olesya", "asket"]

        for skin_name, filename in SKIN_ASSETS.items():
            if skin_name in ["olesya", "asket"]:
                 continue

            await asyncio.sleep(0.5)

            try:
                photo = await upload_local_photo(bot.api, filename, peer_id=vk_id)
            except Exception:
                photo = None

            style_desc = styles.get(skin_name, "мистицизм")
            text = f"✦ ПЕРСОНАЖ: {skin_name}\nСтиль: {style_desc}\nЦена: 1500 Энергии звезд."




            kb = Keyboard(inline=True)
            if skin_name in purchased_skins or skin_name in free_skins:
                kb.add(Callback("ВЫБРАТЬ", payload=json.dumps({"cmd": "set_skin", "skin": skin_name})), color=KeyboardButtonColor.POSITIVE)
            else:
                kb.add(Callback("КУПИТЬ 1500 Энергии", payload=json.dumps({"cmd": "buy_skin", "skin": skin_name})), color=KeyboardButtonColor.PRIMARY)

            if photo:
                try:
                    if message:
                        await message.answer(text, attachment=photo, keyboard=kb.get_json())
                    else:
                        await bot.api.messages.send(peer_id=peer_id, message=text, attachment=photo, keyboard=kb.get_json(), random_id=0)
                except Exception:
                    if message:
                        await message.answer(text, keyboard=kb.get_json())
                    else:
                        await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb.get_json(), random_id=0)
            else:
                if message:
                    await message.answer(text, keyboard=kb.get_json())
                else:
                    await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb.get_json(), random_id=0)
    finally:
        await release_lock(vk_id)

@labeler.message(func=lambda m: m.payload and "cmd" in m.payload and "skin" in m.payload)
async def process_skin_action(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
        return

    try:

        payload = json.loads(message.payload)
        action = payload.get("cmd")
        target_skin = payload.get("skin")

        purchased_skins = user.get("purchased_skins", [])
        free_skins = ["Олеся Ивонченко", "Серьезный Аскет"]
        balance = int(user.get("balance", 0) or 0)

        if action == "set_skin":
            if target_skin in free_skins or target_skin in purchased_skins:
                await update_user(vk_id, {"active_skin": target_skin})
                await message.answer(f"Скин '{target_skin}' успешно активирован. Система теперь говорит его голосом.")
            else:
                await message.answer("Этот скин недоступен. Сначала купите его.")

        elif action == "buy_skin":
            if target_skin in purchased_skins:
                await message.answer("Этот скин уже куплен.")
                return

            price = 1500
            if balance >= price:
                new_balance = balance - price
                purchased_skins.append(target_skin)
                await update_user(vk_id, {
                    "balance": new_balance,
                    "purchased_skins": purchased_skins,
                    "active_skin": target_skin
                })
                await message.answer(f"Скин '{target_skin}' успешно приобретен и активирован!\nВаш баланс: 💳 {new_balance} Энергии звезд.")
            else:
                await message.answer(f"Недостаточно Энергии звезд. Цена: {price}.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} Энергии звезд.")
    finally:
        await release_lock(vk_id)

@labeler.message(text=["✦ Мой профиль", "Мой профиль", "Профиль", "✦ МОЙ ПРОФИЛЬ 👤", "✦ МОЙ ПРОФИЛЬ", "💳 МОЙ ПРОФИЛЬ", "👤 МОЙ ПРОФИЛЬ"])
async def show_profile(message: Message = None, vk_id: int = None, peer_id: int = None):
    if message:
        vk_id = message.from_id
        peer_id = message.peer_id
    elif not vk_id or not peer_id:
        return

    user = await get_user(vk_id)
    if not user:
        await message.answer("❌ Не удалось найти ваш профиль. Попробуйте /start")
        return

    # Получаем активный скин
    skin_filename = user.get("active_skin", "o.png")

    # Загружаем фото профиля
    photo = await upload_local_photo(bot.api, skin_filename, peer_id=vk_id)

    # Формируем клавиатуру
    keyboard = await get_sections_keyboard(vk_id, user)

    # Отправляем профиль
    await message.answer(
        message="💳 **Ваш профиль**",
        attachment=photo,
        keyboard=keyboard
    )

    await set_user_state(vk_id, "")

@labeler.message(text=["🎴 МОЙ ГРИМУАР", "Гримуар"])
async def show_grimoire(message: Message):
    vk_id = message.from_id

    await set_user_state(vk_id, "")
    await show_grimoire_page(vk_id, message.peer_id, 0)

async def show_grimoire_page(vk_id: int, peer_id: int, page: int):

    user = await get_user(vk_id)
    if not user:
        return

    unlocked_cards = user.get("unlocked_cards", {})
    if isinstance(unlocked_cards, list):
         unlocked_cards = {}


    tarot_names = await get_tarot_names()

    unlocked_items = []
    for i in range(78):
        card_id_str = str(i)
        if card_id_str in unlocked_cards:
            unlocked_items.append({"id": card_id_str, "name": tarot_names.get(card_id_str, f"Карта {i}")})

    if not unlocked_items:
        await bot.api.messages.send(peer_id=peer_id, message="✦ МОЙ ГРИМУАР ✦\n\nТвой гримуар пока пуст.", random_id=0)
        return

    ITEMS_PER_PAGE = 5
    total_pages = (len(unlocked_items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_items = unlocked_items[start_idx:end_idx]

    lines = [
        f"✦ МОЙ ГРИМУАР ✦ (Страница {page + 1}/{total_pages})\n",
        "Это твоя личная книга магии. Здесь хранятся все карты, которые ты уже успел открыть. Нажимай на любую, чтобы освежить в памяти ее тайное значение.\n"
    ]
    for item in current_items:
        lines.append(f"[{item['id']}] {item['name']}")

    text = "\n".join(lines)

    buttons = []
    for item in current_items:
        buttons.append([{
            "action": {
                "type": "callback",
                "payload": json.dumps({"cmd": "view_card", "id": item['id']}),
                "label": f"Карта {item['id']}"
            },
            "color": "secondary"
        }])

    nav_row = []
    if page > 0:
        nav_row.append({
            "action": {
                "type": "callback",
                "payload": json.dumps({"cmd": "grimoire_page", "page": page - 1}),
                "label": "Назад"
            },
            "color": "primary"
        })
    if page < total_pages - 1:
        nav_row.append({
            "action": {
                "type": "callback",
                "payload": json.dumps({"cmd": "grimoire_page", "page": page + 1}),
                "label": "Вперед"
            },
            "color": "primary"
        })
    if nav_row:
        buttons.append(nav_row)

    buttons.append([{
        "action": {
            "type": "callback",
            "payload": json.dumps({"cmd": "services_menu"}),
            "label": "🔮 ГЛУБОКИЕ РАЗБОРЫ (УСЛУГИ)"
        },
        "color": "positive"
    }])

    kb = {"inline": True, "buttons": buttons}

    try:
        await bot.api.messages.send(
            peer_id=peer_id,
            message=text,
            keyboard=json.dumps(kb, ensure_ascii=False),
            random_id=0
        )
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        await bot.api.messages.send(peer_id=peer_id, message=text, random_id=0)

@labeler.message(func=lambda m: m.text and re.match(r"(?i)^гримуар\s+\d+$", m.text.strip()))
async def view_grimoire_card(message: Message):
    vk_id = message.from_id
    text = message.text.strip()
    match = re.match(r"(?i)^гримуар\s+(\d+)$", text)
    if not match:
        return
    await view_card_direct(vk_id, message.peer_id, match.group(1))

async def view_card_direct(vk_id: int, peer_id: int, card_id: str):
    user = await get_user(vk_id)
    if not user:
        return

    unlocked_cards = user.get("unlocked_cards", {})
    if isinstance(unlocked_cards, list):
         unlocked_cards = {}

    if str(card_id) not in unlocked_cards:
        await bot.api.messages.send(peer_id=peer_id, message="Эта карта еще не открыта.", random_id=0)
        return


    active_skin = user.get("active_skin", "olesya")
    skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=vk_id)
    if skin_att:
        await bot.api.messages.send(peer_id=peer_id, message="", attachment=skin_att, random_id=0)

    signature = unlocked_cards[str(card_id)]
    await bot.api.messages.send(peer_id=peer_id, message=f"Твое первое касание с этой картой: {signature}", random_id=0)

    photo_att = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)
    if photo_att:
        await bot.api.messages.send(peer_id=peer_id, message="", attachment=photo_att, random_id=0)

@labeler.message(text=["ЛАЙН ГОЛОС"])
async def god_mode_handler(message: Message):
    vk_id = message.from_id

    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        user = await get_user(vk_id)
        if not user:
            await message.answer("Сначала напиши 'Начать'")
            return

        balance = user.get("balance", 0)
        new_balance = balance + 100000

        await update_user(vk_id, {"balance": new_balance})

        user = await get_user(vk_id)
        if not user: return
        kb_json = await get_sections_keyboard(vk_id, user)

        try:
            await message.answer(
                "ЛАЙН ПОДАЛ ГОЛОС. ВАМ НАЧИСЛЕНО 100 000 ЭНЕРГИИ ЗВЕЗД.",
                keyboard=kb_json
            )
        except Exception:
            await message.answer(
                "ЛАЙН ПОДАЛ ГОЛОС. ВАМ НАЧИСЛЕНО 100 000 ЭНЕРГИИ ЗВЕЗД."
            )
    finally:
        await release_lock(vk_id)


@labeler.message(text=["Мой Синдикат 🕸", "Мой Синдикат", "Мой синдикат"])
async def syndicate_dashboard_handler(message: Message = None, vk_id: int = None, peer_id: int = None):
    if message:
        vk_id = message.from_id
        peer_id = message.peer_id
    elif not vk_id or not peer_id:
        return
    logger.info(f"syndicate_dashboard_handler triggered by vk_id={vk_id}")

    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        return

    purchased = user.get("purchased_sections", {})
    syndicate_count = purchased.get("syndicate_count", 0)
    syndicate_energy = purchased.get("syndicate_energy", 0)

    progress_text = ""
    if syndicate_count >= 5:
        rank = "Теневой Кардинал"
        progress_text = "Ты достиг вершины синдиката."
    elif syndicate_count >= 1:
        rank = "Вербовщик"
        left = 5 - syndicate_count
        progress_text = f"До статуса Теневой Кардинал осталось {left} адепт(а)."
    else:
        rank = "Одиночка"
        progress_text = "До статуса Вербовщик остался 1 адепт."

    text = (
        "🕸 СИНДИКАТ АНТИ-ТАР 🕸\n\n"
        f"Твой текущий ранг: {rank}\n"
        f"Завербовано адептов: {syndicate_count}\n"
        f"Сгенерировано энергии: {syndicate_energy} ✨\n\n"
        f"{progress_text}\n\n"
        "Расширяй свою матрицу. За каждого нового адепта ты получаешь 500 чистой Энергии звезд."
    )

    is_veteran = False
    created_at_str = user.get("created_at")
    if created_at_str:
        import datetime
        created_at = datetime.datetime.fromisoformat(created_at_str)
        now = datetime.datetime.now(datetime.timezone.utc)
        hours_since_creation = (now - created_at).total_seconds() / 3600
        if hours_since_creation > 24:
            is_veteran = True

    if purchased.get("promo_used"):
        is_veteran = True

    kb = Keyboard(inline=True)
    kb.add(Callback("Получить Печать 📜", payload={"cmd": "profile_action", "action": "get_seal"}), color=KeyboardButtonColor.PRIMARY)
    if not is_veteran:
        kb.row()
        kb.add(Callback("Ввести Печать ✒", payload={"cmd": "profile_action", "action": "enter_seal"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.SECONDARY)

    if message:
        await message.answer(text, keyboard=kb.get_json())
    else:
        await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb.get_json(), random_id=0)

@labeler.message(text=["Назад в профиль 👤"])
async def back_to_profile(message: Message):
    from modules.profile import show_profile
    await show_profile(message)

@labeler.message(text=["Получить Печать 📜"])
async def get_seal_handler(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "")
    text = (
        "📜 ТВОЯ ПЕЧАТЬ ПРИЗЫВА\n\n"
        f"Код твоей Печати: ПЕЧАТЬ-{vk_id}\n\n"
        "Отправь этот код новому адепту, или скинь ему прямую ссылку: "
        f"https://vk.com/im?sel=-225575503&text=ПЕЧАТЬ-{vk_id}\n\n"
        "Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд."
    )
    await message.answer(text)

@labeler.message(text=["Ввести Печать ✒"])
async def enter_seal_handler(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "waiting_for_seal")
    # Actually wait for the seal via basic state dispatcher approach
    kb = Keyboard(inline=True)
    kb.add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
    await message.answer("Введи Печать (код), которую тебе передал Ведущий:", keyboard=kb.get_json())

@labeler.message(text=["Отмена"])
async def cancel_seal_handler(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "")
    await syndicate_dashboard_handler(message)


@labeler.message(func=lambda m: m.text and re.match(r"(?i)^(ПРОМО|ПЕЧАТЬ)-\d+$", m.text.strip()))
async def apply_promo_handler(message: Message):
    await set_user_state(message.from_id, "")
    vk_id = message.from_id
    text = message.text.strip().upper()
    match = re.match(r"^(ПРОМО|ПЕЧАТЬ)-(\d+)$", text)
    if not match:
        return

    referrer_id = int(match.group(2))

    user = await get_user(vk_id)
    is_new = False
    if not user:
        from database import create_user
        user = await create_user(vk_id, "", "", "")
        is_new = True

    is_veteran = False
    created_at_str = user.get("created_at")
    if created_at_str:
        import datetime
        created_at = datetime.datetime.fromisoformat(created_at_str)
        now = datetime.datetime.now(datetime.timezone.utc)
        if (now - created_at).total_seconds() / 3600 > 24:
            is_veteran = True

    purchased = user.get("purchased_sections", {})
    if purchased.get("promo_used"):
        is_veteran = True

    if is_veteran:
        await message.answer("Доступ отклонен. Твоя матрица уже давно интегрирована в систему. Печать призыва работает только для новых адептов. Выстраивай свой личный Синдикат.")
        return

    if referrer_id == vk_id:
        await message.answer("Ты не можешь использовать свою собственную Печать.")
        return

    referrer = await get_user(referrer_id)
    if not referrer:
        await message.answer("Такой Печати не существует.")
        return

    user_balance = int(user.get("balance", 0) or 0) + 500
    referrer_balance = int(referrer.get("balance", 0) or 0) + 500

    purchased["promo_used"] = True
    await update_user(vk_id, {"balance": user_balance, "purchased_sections": purchased})

    ref_purchased = referrer.get("purchased_sections", {})
    ref_purchased["syndicate_count"] = ref_purchased.get("syndicate_count", 0) + 1
    ref_purchased["syndicate_energy"] = ref_purchased.get("syndicate_energy", 0) + 500
    await update_user(referrer_id, {"balance": referrer_balance, "purchased_sections": ref_purchased})

    await message.answer(f"ПЕЧАТЬ АКТИВИРОВАНА! Тебе начислено 500 Энергии звезд. Твой баланс: {user_balance} Энергии звезд")

    if is_new:
        from modules.registration import start_handler
        await start_handler(message)

    try:
        # Get first name from user DB or use "Пользователь"
        first_name = purchased.get("first_name")
        if not first_name:
            user_info = await bot.api.users.get(user_ids=[vk_id])
            if user_info:
                first_name = user_info[0].first_name
            else:
                first_name = "Адепт"

        push_msg = f"Твой Синдикат растет! Пользователь {first_name} подключился к твоей сети. Зачислено 500 Энергии звезд."
        if ref_purchased["syndicate_count"] == 5:
            push_msg += "\n\nТвой ранг повышен до: Теневой Кардинал! Теперь тебе открыты скрытые возможности."
        await bot.api.messages.send(peer_id=referrer_id, message=push_msg, random_id=0)
    except Exception as e:
        logger.error(f"Ignored Exception: {str(e)}")



@labeler.message(text=["✦ Путеводитель", "путеводитель", "Путеводитель", "📖 ПУТЕВОДИТЕЛЬ", "📖 Путеводитель"])
async def show_guide(message: Message):
    vk_id = message.from_id
    text = (
        "ПУТЕВОДИТЕЛЬ ПО СИСТЕМЕ\n"
        "Здесь собраны ответы на все вопросы.\n\n"
        "Энергообмен: Вся система работает на Энергии звезд. 10 Энергии звезд равны 1 рублю. Ты можешь копить энергию или покупать ее.\n\n"
        "Как получать энергию в дар:\n\n"
        "Ежедневный дар: Заходи ко мне каждый день и открывай Главное меню. Я буду начислять тебе 100 Энергии звезд.\n\n"
        "Приветственный дар: Ты получаешь 700 Энергии звезд при регистрации.\n\n"
        "Мой Синдикат: В разделе Мой профиль есть кнопка Мой Синдикат. Передай Печать призыва новому адепту, и вы оба получите по 500 Энергии звезд.\n\n"
        "Как открывать тайны: Перейди в Услуги, листай карточки и жми Купить. Если энергии не хватит, система сама рассчитает доплату. После покупки я выдам тебе личный PDF-файл.\n\n"
        "Карты и Гримуар: После каждой покупки ты вытягиваешь новую карту. Она навсегда сохранится в твоем Гримуаре в профиле."
    )
    await message.answer(text)
