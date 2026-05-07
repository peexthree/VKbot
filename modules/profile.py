from modules.bot_init import bot
from cache import acquire_lock, release_lock
import asyncio
import json
import datetime

import random
import re

from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader, Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user, delete_user
from modules.states import MyStates
from cache import get_tarot_names
from modules.utils import SKIN_ASSETS
import datetime
from ai_service import generate_text, generate_section
from modules.utils import get_fsm_step, upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, get_storefront_keyboard, cover_cache
from loguru import logger

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
async def settings_handler(message: Message):
    vk_id = message.from_id

    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        text = "✦ НАСТРОЙКИ И ЮРИДИЧЕСКИЙ ЩИТ ✦"

        kb = Keyboard(inline=True)
        kb.add(Text("Изменить свои данные"), color=KeyboardButtonColor.SECONDARY)
        kb.row()
        kb.add(Text("Выбрать персонажа"), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Text("Отменить подписку"), color=KeyboardButtonColor.SECONDARY)
        kb.row()
        kb.add(Text("СБРОС АККАУНТА"), color=KeyboardButtonColor.NEGATIVE)
        kb.row()
        kb.add(Text("Назад в профиль"), color=KeyboardButtonColor.PRIMARY)

        await message.answer(text, keyboard=kb.get_json())
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
        kb.add(Text("ПОДТВЕРДИТЬ СБРОС"), color=KeyboardButtonColor.NEGATIVE)
        kb.row()
        kb.add(Text("Назад в профиль"), color=KeyboardButtonColor.PRIMARY)

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
async def settings_choose_character(message: Message):
    vk_id = message.from_id

    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    try:
        user = await get_user(vk_id)
        if not user:
            await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
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
            "Григорий Распутин": "безумие"
        }

        free_skins = ["Олеся Ивонченко", "Серьезный Аскет", "olesya", "asket"]

        for skin_name, filename in SKIN_ASSETS.items():
            if skin_name in ["olesya", "asket"]:
                 continue

            await asyncio.sleep(0.5)

            try:
                photo = await upload_local_photo(bot.api, filename)
            except Exception as e:
                photo = None

            style_desc = styles.get(skin_name, "мистицизм")
            text = f"✦ ПЕРСОНАЖ: {skin_name}\nСтиль: {style_desc}\nЦена: 1500 Энергии звезд."




            kb = Keyboard(inline=True)
            if skin_name in purchased_skins or skin_name in free_skins:
                kb.add(Text("ВЫБРАТЬ", payload=json.dumps({"cmd": "set_skin", "skin": skin_name})), color=KeyboardButtonColor.POSITIVE)
            else:
                kb.add(Text("КУПИТЬ 1500 Энергии", payload=json.dumps({"cmd": "buy_skin", "skin": skin_name})), color=KeyboardButtonColor.PRIMARY)

            if photo:
                try:
                    await message.answer(text, attachment=photo, keyboard=kb.get_json())
                except Exception as e:
                    await message.answer(text, keyboard=kb.get_json())
            else:
                await message.answer(text, keyboard=kb.get_json())
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

@labeler.message(text=["✦ Мой профиль", "Мой профиль", "✦ МОЙ ПРОФИЛЬ 👤", "✦ МОЙ ПРОФИЛЬ", "💳 МОЙ ПРОФИЛЬ"])
async def show_profile(message: Message):



    vk_id = message.from_id

    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
        return

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
            days_in_matrix = 0

    unlocked_cards = user.get("unlocked_cards", {})
    if isinstance(unlocked_cards, list):
         unlocked_cards = {}
    cards_count = len(unlocked_cards)
    total_cards_received = cards_count

    bars = min(10, int((cards_count / 78) * 10))
    progress_bar = ("|" * bars) + ("." * (10 - bars))

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
        except ValueError as e:
            logger.error(f"Ignored Exception: {str(e)}")

    profile_text = (
        f"✦ ЛИЧНАЯ КАРТА ✦\n"
        f"👤 ИМЯ: {first_name}\n"
        f"📍 ТОЧКА ВХОДА: {birth_date} - {birth_city}\n"
        f"⏳ ДНЕЙ В ОСОЗНАННОСТИ: {days_in_matrix}\n"
        f"🎴 СОБРАНО КАРТ: {total_cards_received} из 78\n"
        f"📊 ПРОГРЕСС: {progress_bar}\n"
        f"💳 БАЛАНС: {balance} Энергии звезд\n"
        f"🛡 СТАТУС: {status}\n"
        f"📡 ТРАНЗИТ: {transit_status}\n"
        f"🕙 ДОСТУП ДО: {transit_timer}\n\n"
    )

    purchased = user.get("purchased_sections", {})
    if status == "Спящий":
        profile_text += "✨ Твоя энергия на нуле. Открой 'Карта дня', чтобы пробудиться и запустить энергообмен!\n\n"
    elif purchased.get("sex") and not purchased.get("money"):
        profile_text += "✨ Рекомендуем продолжить погружение с разделом 'Код твоего богатства'\n\n"

    profile_text += f"Оплачивая услуги, вы принимаете условия Публичной оферты: https://telegra.ph/PUBLICHNAYA-OFERTA-NA-OKAZANIE-INFORMACIONNO-RAZVLEKATELNYH-USLUG-05-04"

    kb = Keyboard(inline=True)
    kb.add(Text("✦ Настройки ⚙"), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("Позвать друга 👥"), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("🎴 МОЙ ГРИМУАР"), color=KeyboardButtonColor.PRIMARY)

    active_skin = user.get("active_skin", "olesya")
    skin_filename = SKIN_ASSETS.get(active_skin, "o.png")
    photo = await upload_local_photo(bot.api, skin_filename)

    try:
        if photo:
            await message.answer(profile_text, attachment=photo, keyboard=kb.get_json())
        else:
            await message.answer(profile_text, keyboard=kb.get_json())
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        try:
             if photo:
                  await message.answer(profile_text, attachment=photo)
             else:
                  await message.answer(profile_text)
        except Exception as e:
             logger.error(f"Ignored Exception: {str(e)}")

@labeler.message(text=["🎴 МОЙ ГРИМУАР"])
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
    skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"))
    if skin_att:
        await bot.api.messages.send(peer_id=peer_id, message="", attachment=skin_att, random_id=0)

    signature = unlocked_cards[str(card_id)]
    await bot.api.messages.send(peer_id=peer_id, message=f"Твое первое касание с этой картой: {signature}", random_id=0)

    photo_att = await upload_local_photo(bot.api, f"{card_id}.jpeg")
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
        kb_json = await get_sections_keyboard(vk_id, user)

        try:
            await message.answer(
                "ЛАЙН ПОДАЛ ГОЛОС. ВАМ НАЧИСЛЕНО 100 000 ЭНЕРГИИ ЗВЕЗД.",
                keyboard=kb_json
            )
        except Exception as e:
            await message.answer(
                "ЛАЙН ПОДАЛ ГОЛОС. ВАМ НАЧИСЛЕНО 100 000 ЭНЕРГИИ ЗВЕЗД."
            )
    finally:
        await release_lock(vk_id)


@labeler.message(text=["Слить друга", "✦ Слить друга", "Позвать друга 👥", "✦ Позвать друга 👥"])
async def referral_handler(message: Message):
    vk_id = message.from_id
    logger.info(f"referral_handler triggered by vk_id={vk_id}")

    await set_user_state(vk_id, "")
    await message.answer(f"✦ РЕФЕРАЛЬНАЯ СИСТЕМА ✦\n\nТвой промокод: ПРОМО-{vk_id}\n\nОтправь этот код другу. Если он напишет его мне, вы оба получите по 500 Энергии звезд!")

@labeler.message(func=lambda m: m.text and re.match(r"^ПРОМО-\d+$", m.text.strip()))
async def apply_promo_handler(message: Message):
    vk_id = message.from_id
    text = message.text.strip()
    match = re.match(r"^ПРОМО-(\d+)$", text)
    if not match:
        return

    referrer_id = int(match.group(1))
    if referrer_id == vk_id:
        await message.answer("Ты не можешь использовать свой собственный промокод.")
        return

    user = await get_user(vk_id)
    if not user:
        await message.answer("Сначала зарегистрируйся в системе (напиши Начать).")
        return

    referrer = await get_user(referrer_id)
    if not referrer:
        await message.answer("Такого промокода не существует.")
        return

    purchased = user.get("purchased_sections", {})
    if purchased.get("promo_used"):
        await message.answer("Вы уже использовали промокод.")
        return

    user_balance = int(user.get("balance", 0) or 0) + 500
    referrer_balance = int(referrer.get("balance", 0) or 0) + 500

    purchased["promo_used"] = True
    await update_user(vk_id, {"balance": user_balance, "purchased_sections": purchased})
    await update_user(referrer_id, {"balance": referrer_balance})

    await message.answer(f"ПРОМОКОД АКТИВИРОВАН! Тебе начислено 500 Энергии звезд. Твой баланс: {user_balance} Энергии звезд")

    try:
        await bot.api.messages.send(peer_id=referrer_id, message=f"Твой друг активировал промокод! Тебе начислено 500 Энергии звезд. Твой баланс: {referrer_balance} Энергии звезд", random_id=0)
    except Exception as e:
        logger.error(f"Ignored Exception: {str(e)}")


@labeler.message(text=["✦ Путеводитель", "путеводитель", "Путеводитель", "📖 Путеводитель"])
async def show_guide(message: Message):
    vk_id = message.from_id
    text = (
        "ПУТЕВОДИТЕЛЬ ПО СИСТЕМЕ\n"
        "Здесь собраны ответы на все вопросы.\n\n"
        "Энергообмен: Вся система работает на Энергии звезд. 10 Энергии звезд равны 1 рублю. Ты можешь копить энергию или покупать ее.\n\n"
        "Как получать энергию в дар:\n\n"
        "Ежедневный дар: Заходи ко мне каждый день и открывай Главное меню. Я буду начислять тебе 100 Энергии звезд.\n\n"
        "Приветственный дар: Ты получаешь 700 Энергии звезд при регистрации.\n\n"
        "Зови друзей: В разделе Мой профиль есть кнопка Позвать друга с твоим промокодом. Если подруга отправит его мне, вы обе получите по 500 Энергии звезд.\n\n"
        "Как открывать тайны: Перейди в Услуги, листай карточки и жми Купить. Если энергии не хватит, система сама рассчитает доплату. После покупки я выдам тебе личный PDF-файл.\n\n"
        "Карты и Гримуар: После каждой покупки ты вытягиваешь новую карту. Она навсегда сохранится в твоем Гримуаре в профиле."
    )
    await message.answer(text)
