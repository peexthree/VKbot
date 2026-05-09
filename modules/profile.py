from __future__ import annotations
import datetime
import json
import os
import re
from loguru import logger
from vkbottle import Callback, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message

from cache import acquire_lock, get_tarot_names, release_lock
from database import delete_user, get_user, set_user_state, update_user
from modules.bot_init import bot
from modules.utils import SKIN_ASSETS, get_sections_keyboard, start_dynamic_typing, upload_local_photo

labeler = BotLabeler()

ADMIN_ID = int(os.environ.get("ADMIN_ID", 27260796))


# ====================== УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ДЕЙСТВИЙ ======================
@labeler.callback(payload={"cmd": "profile_action"})
async def profile_action_handler(event):
    vk_id = event.user_id
    peer_id = event.peer_id
    action = event.payload.get("action")

    if not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id)

        if action == "settings":
            await show_settings(vk_id, peer_id, event.message_id)
        elif action == "change_data":
            await change_data(vk_id, peer_id)
        elif action == "change_skin":
            await show_skin_selection(vk_id, peer_id)
        elif action == "cancel_sub":
            await cancel_subscription(vk_id, peer_id)
        elif action == "reset_account":
            await request_reset_account(vk_id, peer_id)
        elif action == "confirm_reset":
            await confirm_reset_account(vk_id, peer_id)
        elif action == "back_to_profile":
            await show_profile(Message(from_id=vk_id, peer_id=peer_id))
        elif action == "admin_console":
            await bot.api.messages.send(peer_id=peer_id, message="Консоль Магистра в разработке", random_id=0)
        elif action == "syndicate":
            await syndicate_dashboard_handler(Message(from_id=vk_id, peer_id=peer_id))
        elif action == "grimoire":
            await show_grimoire(Message(from_id=vk_id, peer_id=peer_id))
        elif action == "tariffs":
            # Прямой вызов хендлера из services.py
            await bot.labeler.get_handler_by_text("🛰 ТАРИФЫ")(Message(from_id=vk_id, peer_id=peer_id))
        elif action == "get_seal":
            await get_seal_handler(Message(from_id=vk_id, peer_id=peer_id))
        elif action == "enter_seal":
            await enter_seal_handler(Message(from_id=vk_id, peer_id=peer_id))
        elif action == "cancel_seal":
            await cancel_seal_handler(Message(from_id=vk_id, peer_id=peer_id))
    finally:
        await release_lock(vk_id)


# ====================== БАЛАНС ======================
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


# ====================== НАСТРОЙКИ ======================
async def show_settings(vk_id: int, peer_id: int, edit_msg_id: int | None = None):
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

    if edit_msg_id:
        await bot.api.messages.edit(peer_id=peer_id, message_id=edit_msg_id, message=text, keyboard=kb.get_json())
    else:
        await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb.get_json(), random_id=0)


async def change_data(vk_id: int, peer_id: int):
    await set_user_state(vk_id, json.dumps({"step": "date"}))
    await bot.api.messages.send(peer_id=peer_id, message="Укажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):", random_id=0)


async def cancel_subscription(vk_id: int, peer_id: int):
    await bot.api.messages.send(
        peer_id=peer_id,
        message="Ваш аккаунт не имеет активных рекуррентных подписок. Все платежи разовые. Для прекращения получения транзитов просто не пополняйте баланс.",
        random_id=0
    )


async def request_reset_account(vk_id: int, peer_id: int):
    await set_user_state(vk_id, json.dumps({"step": "waiting_reset_confirm"}))
    kb = Keyboard(inline=True)
    kb.add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
    await bot.api.messages.send(
        peer_id=peer_id,
        message="⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс. Вы уверены?",
        keyboard=kb.get_json(),
        random_id=0
    )


async def confirm_reset_account(vk_id: int, peer_id: int):
    await delete_user(vk_id)
    await set_user_state(vk_id, "")
    await bot.api.messages.send(peer_id=peer_id, message="Система обнулена. Напишите 'Начать', чтобы заново войти в матрицу.", random_id=0)


# ====================== ПРОФИЛЬ ======================
@labeler.message(text=["✦ Мой профиль", "Мой профиль", "✦ МОЙ ПРОФИЛЬ 👤", "✦ МОЙ ПРОФИЛЬ", "💳 МОЙ ПРОФИЛЬ"])
async def show_profile(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, message.peer_id)
        user = await get_user(vk_id)
        if not user:
            await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
            return

        # ... (весь расчёт profile_text — оставлен как был, он правильный)
        first_name = user.get("purchased_sections", {}).get("first_name", "Неизвестно")
        birth_date = user.get("birth_date", "Неизвестно")
        birth_city = user.get("birth_city", "Неизвестно")
        created_at_str = user.get("created_at")
        days_in_matrix = 0
        if created_at_str:
            try:
                created_at = datetime.datetime.fromisoformat(created_at_str)
                days_in_matrix = (datetime.datetime.now(datetime.timezone.utc) - created_at).days
            except ValueError:
                pass

        unlocked_cards = user.get("unlocked_cards", {}) or {}
        cards_count = len(unlocked_cards)
        bars = min(10, int((cards_count / 78) * 10))
        progress_bar = "█" * bars + "░" * (10 - bars)

        balance = int(user.get("balance", 0) or 0)
        status = "Пробужденный" if balance > 0 else "Спящий"

        transit_expires = user.get("transit_sub_expires_at")
        transit_status = "Базовый"
        transit_timer = "Отсутствует"
        if transit_expires:
            try:
                exp_date = datetime.datetime.fromisoformat(transit_expires)
                if exp_date > datetime.datetime.now(datetime.timezone.utc):
                    transit_status = "Активен"
                    transit_timer = exp_date.strftime("%d.%m.%Y")
            except ValueError:
                pass

        profile_text = (
            f"✦ ЛИЧНАЯ КАРТА ✦\n"
            f"👤 ИМЯ: {first_name}\n"
            f"📍 ТОЧКА ВХОДА: {birth_date} - {birth_city}\n"
            f"⏳ ДНЕЙ В ОСОЗНАННОСТИ: {days_in_matrix}\n"
            f"🎴 СОБРАНО КАРТ: {cards_count} из 78\n"
            f"📊 ПРОГРЕСС: {progress_bar}\n"
            f"💳 БАЛАНС: {balance} Энергии звезд\n"
            f"🛡 СТАТУС: {status}\n"
            f"📡 ТРАНЗИТ: {transit_status}\n"
            f"🕙 ДОСТУП ДО: {transit_timer}\n\n"
        )
        if status == "Спящий":
            profile_text += "✨ Твоя энергия на нуле. Открой 'Карта дня', чтобы пробудиться!\n\n"
        profile_text += "Оплачивая услуги, вы принимаете условия Публичной оферты: https://telegra.ph/PUBLICHNAYA-OFERTA-NA-OKAZANIE-INFORMACIONNO-RAZVLEKATELNYH-USLUG-05-04"

        kb = Keyboard(inline=True)
        kb.add(Callback("✦ Настройки ⚙", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.SECONDARY)
        if vk_id == ADMIN_ID:
            kb.row()
            kb.add(Callback("⚙️ КОНСОЛЬ МАГИСТРА", payload={"cmd": "profile_action", "action": "admin_console"}), color=KeyboardButtonColor.PRIMARY)
        kb.add(Callback("Мой Синдикат 🕸", payload={"cmd": "profile_action", "action": "syndicate"}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
        kb.add(Callback("🎴 МОЙ ГРИМУАР", payload={"cmd": "profile_action", "action": "grimoire"}), color=KeyboardButtonColor.PRIMARY)
        kb.add(Callback("🛰 ТАРИФЫ", payload={"cmd": "profile_action", "action": "tariffs"}), color=KeyboardButtonColor.PRIMARY)

        active_skin = user.get("active_skin", "olesya")
        skin_filename = SKIN_ASSETS.get(active_skin, "o.png")
        photo = await upload_local_photo(bot.api, skin_filename, peer_id=message.peer_id)

        if photo:
            await message.answer(profile_text, attachment=photo, keyboard=kb.get_json())
        else:
            await message.answer(profile_text, keyboard=kb.get_json())
    finally:
        await release_lock(vk_id)


# ====================== ВЫБОР СКИНА ======================
async def show_skin_selection(vk_id: int, peer_id: int):
    user = await get_user(vk_id)
    if not user:
        return
    purchased_skins = user.get("purchased_skins", [])
    free_skins = ["Олеся Ивонченко", "Серьезный Аскет", "olesya", "asket"]

    kb = Keyboard(inline=True)
    for skin_name, _filename in SKIN_ASSETS.items():
        style = {
            "olesya": "сарказм", "Олеся Ивонченко": "сарказм",
            "asket": "строгость", "Серьезный Аскет": "строгость",
            "Влад Череватов": "дерзость", "Виктория Райдес": "властность",
            "Олег Шэпс": "загадочность", "Александр Шеппс": "мистицизм",
            "Баба Ванга": "пророчества", "Григорий Распутин": "безумие"
        }.get(skin_name, "мистицизм")

        if skin_name in free_skins or skin_name in purchased_skins:
            kb.add(Callback(f"ВЫБРАТЬ {skin_name}", payload={"cmd": "set_skin", "skin": skin_name}), color=KeyboardButtonColor.POSITIVE)
        else:
            kb.add(Callback(f"КУПИТЬ 1500 Энергии — {skin_name}", payload={"cmd": "buy_skin", "skin": skin_name}), color=KeyboardButtonColor.PRIMARY)
        kb.row()

    kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.SECONDARY)

    await bot.api.messages.send(
        peer_id=peer_id,
        message="✦ ВЫБЕРИ ПЕРСОНАЖА ✦\nКаждый говорит своим голосом.",
        keyboard=kb.get_json(),
        random_id=0
    )


# ====================== ОБРАБОТКА СКИНОВ ======================
@labeler.message(func=lambda m: m.payload and "cmd" in m.payload and m.payload.get("cmd") in ["set_skin", "buy_skin"])
async def process_skin_action(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        payload = json.loads(message.payload)
        action = payload.get("cmd")
        target_skin = payload.get("skin")
        user = await get_user(vk_id)
        if not user:
            return

        purchased_skins = user.get("purchased_skins", [])
        free_skins = ["Олеся Ивонченко", "Серьезный Аскет"]
        balance = int(user.get("balance", 0) or 0)

        if action == "set_skin":
            if target_skin in free_skins or target_skin in purchased_skins:
                await update_user(vk_id, {"active_skin": target_skin})
                await message.answer(f"Скин '{target_skin}' успешно активирован.")
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
                await message.answer(f"Скин '{target_skin}' приобретён и активирован!\nБаланс: {new_balance} Энергии звезд.")
            else:
                await message.answer(f"Недостаточно энергии. Нужно {price}, у тебя {balance}.")
    finally:
        await release_lock(vk_id)


# ====================== ГРИМУАР ======================
# (твой код гримуара оставлен без изменений — он работает)

@labeler.message(text=["🎴 МОЙ ГРИМУАР"])
async def show_grimoire(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "")
    await show_grimoire_page(vk_id, message.peer_id, 0)


async def show_grimoire_page(vk_id: int, peer_id: int, page: int):
    user = await get_user(vk_id)
    if not user:
        return
    unlocked_cards = user.get("unlocked_cards", {}) or {}
    tarot_names = await get_tarot_names()

    unlocked_items = [
        {"id": str(i), "name": tarot_names.get(str(i), f"Карта {i}")}
        for i in range(78) if str(i) in unlocked_cards
    ]

    if not unlocked_items:
        await bot.api.messages.send(peer_id=peer_id, message="✦ МОЙ ГРИМУАР ✦\n\nТвой гримуар пока пуст.", random_id=0)
        return

    ITEMS_PER_PAGE = 5
    total_pages = (len(unlocked_items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(0, min(page, total_pages - 1))
    start = page * ITEMS_PER_PAGE
    current_items = unlocked_items[start:start + ITEMS_PER_PAGE]

    lines = [f"✦ МОЙ ГРИМУАР ✦ (Страница {page + 1}/{total_pages})\n"]
    lines.append("Нажимай на карту, чтобы освежить её значение.\n")
    for item in current_items:
        lines.append(f"[{item['id']}] {item['name']}")

    kb = Keyboard(inline=True)
    for item in current_items:
        kb.add(Callback(f"Карта {item['id']}", payload={"cmd": "view_card", "id": item['id']}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

    if page > 0:
        kb.add(Callback("Назад", payload={"cmd": "grimoire_page", "page": page - 1}), color=KeyboardButtonColor.PRIMARY)
    if page < total_pages - 1:
        kb.add(Callback("Вперёд", payload={"cmd": "grimoire_page", "page": page + 1}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🔮 Услуги", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)

    await bot.api.messages.send(peer_id=peer_id, message="\n".join(lines), keyboard=kb.get_json(), random_id=0)


@labeler.message(func=lambda m: m.payload and m.payload.get("cmd") == "view_card")
async def view_card_callback(event):
    await view_card_direct(event.user_id, event.peer_id, event.payload.get("id"))


async def view_card_direct(vk_id: int, peer_id: int, card_id: str):
    user = await get_user(vk_id)
    if not user or str(card_id) not in (user.get("unlocked_cards") or {}):
        await bot.api.messages.send(peer_id=peer_id, message="Эта карта ещё не открыта.", random_id=0)
        return

    active_skin = user.get("active_skin", "olesya")
    skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=peer_id)
    if skin_att:
        await bot.api.messages.send(peer_id=peer_id, message="", attachment=skin_att, random_id=0)

    signature = user["unlocked_cards"][str(card_id)]
    await bot.api.messages.send(peer_id=peer_id, message=f"Твоё первое касание с этой картой: {signature}", random_id=0)

    photo_att = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=peer_id)
    if photo_att:
        await bot.api.messages.send(peer_id=peer_id, message="", attachment=photo_att, random_id=0)


# ====================== GOD MODE ======================
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
        new_balance = int(user.get("balance", 0) or 0) + 100000
        await update_user(vk_id, {"balance": new_balance})
        kb_json = await get_sections_keyboard(vk_id, user)
        await message.answer("ЛАЙН ПОДАЛ ГОЛОС. ВАМ НАЧИСЛЕНО 100 000 ЭНЕРГИИ ЗВЕЗД.", keyboard=kb_json)
    finally:
        await release_lock(vk_id)


# ====================== СИНДИКАТ ======================
@labeler.message(text=["Мой Синдикат 🕸", "Мой Синдикат", "Мой синдикат"])
async def syndicate_dashboard_handler(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        return

    purchased = user.get("purchased_sections", {})
    syndicate_count = purchased.get("syndicate_count", 0)
    syndicate_energy = purchased.get("syndicate_energy", 0)

    if syndicate_count >= 5:
        rank = "Теневой Кардинал"
        progress_text = "Ты достиг вершины синдиката."
    elif syndicate_count >= 1:
        rank = "Вербовщик"
        progress_text = f"До Теневого Кардинала осталось {5 - syndicate_count} адепта."
    else:
        rank = "Одиночка"
        progress_text = "До Вербовщика остался 1 адепт."

    text = (
        "🕸 СИНДИКАТ АНТИ-ТАР 🕸\n\n"
        f"Твой текущий ранг: {rank}\n"
        f"Завербовано адептов: {syndicate_count}\n"
        f"Сгенерировано энергии: {syndicate_energy} ✨\n\n"
        f"{progress_text}\n\n"
        "За каждого нового адепта ты получаешь 500 Энергии звезд."
    )

    kb = Keyboard(inline=True)
    kb.add(Callback("Получить Печать 📜", payload={"cmd": "profile_action", "action": "get_seal"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("Ввести Печать ✒", payload={"cmd": "profile_action", "action": "enter_seal"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("Назад в профиль 👤", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.SECONDARY)

    await message.answer(text, keyboard=kb.get_json())


# ====================== ПЕЧАТЬ ======================
@labeler.message(text=["Получить Печать 📜"])
async def get_seal_handler(message: Message):
    vk_id = message.from_id
    text = (
        "📜 ТВОЯ ПЕЧАТЬ ПРИЗЫВА\n\n"
        f"Код твоей Печати: ПЕЧАТЬ-{vk_id}\n\n"
        f"Ссылка: https://vk.com/im?sel=-225575503&text=ПЕЧАТЬ-{vk_id}"
    )
    await message.answer(text)


@labeler.message(text=["Ввести Печать ✒"])
async def enter_seal_handler(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "waiting_for_seal")
    kb = Keyboard(inline=True)
    kb.add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
    await message.answer("Введи Печать (код), которую тебе передал Ведущий:", keyboard=kb.get_json())


@labeler.message(text=["Отмена"])
async def cancel_seal_handler(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "")
    await syndicate_dashboard_handler(message)


# ====================== ПРИМЕНЕНИЕ ПЕЧАТИ / ПРОМО ======================
@labeler.message(func=lambda m: m.text and re.match(r"(?i)^(ПРОМО|ПЕЧАТЬ)-\d+$", m.text.strip()))
async def apply_promo_handler(message: Message):
    vk_id = message.from_id
    await set_user_state(vk_id, "")
    text = message.text.strip().upper()
    match = re.match(r"^(ПРОМО|ПЕЧАТЬ)-(\d+)$", text)
    if not match:
        return

    referrer_id = int(match.group(2))
    user = await get_user(vk_id)
    if not user:
        await message.answer("Сначала зарегистрируйся в системе (напиши Начать).")
        return

    is_veteran = False
    created_at_str = user.get("created_at")
    if created_at_str:
        try:
            created_at = datetime.datetime.fromisoformat(created_at_str)
            now = datetime.datetime.now(datetime.timezone.utc)
            if (now - created_at).total_seconds() / 3600 > 24:
                is_veteran = True
        except ValueError:
            pass

    purchased = user.get("purchased_sections", {})
    if purchased.get("promo_used"):
        is_veteran = True

    if is_veteran:
        await message.answer("Доступ отклонен. Твоя матрица уже давно интегрирована в систему. Печать призыва работает только для новых адептов.")
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

    try:
        first_name = user.get("purchased_sections", {}).get("first_name") or "Адепт"
        push_msg = f"Твой Синдикат растет! Пользователь {first_name} подключился. +500 Энергии звезд."
        if ref_purchased["syndicate_count"] == 5:
            push_msg += "\n\nТвой ранг повышен до: Теневой Кардинал!"
        await bot.api.messages.send(peer_id=referrer_id, message=push_msg, random_id=0)
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление рефереру: {e}")


# ====================== ПУТЕВОДИТЕЛЬ ======================
@labeler.message(text=["✦ Путеводитель", "путеводитель", "Путеводитель", "📖 ПУТЕВОДИТЕЛЬ", "📖 Путеводитель"])
async def show_guide(message: Message):
    text = (
        "ПУТЕВОДИТЕЛЬ ПО СИСТЕМЕ\n"
        "Здесь собраны ответы на все вопросы.\n\n"
        "Энергообмен: 10 Энергии звезд = 1 рубль.\n\n"
        "Ежедневный дар: +100 Энергии каждый день.\n"
        "Мой Синдикат: Приглашай адептов — получай 500 энергии за каждого.\n"
        "Гримуар: Все открытые карты сохраняются навсегда."
    )
    await message.answer(text)


# ====================== ЗАВЕРШЕНИЕ ФАЙЛА ======================
logger.info("Модуль profile.py загружен успешно")
