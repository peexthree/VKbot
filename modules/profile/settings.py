import json
import asyncio
from vkbottle.bot import Message
from modules.bot_init import bot
from database import get_user, update_user, set_user_state, delete_user
from cache import acquire_lock, release_lock
from modules.utils import SKIN_ASSETS, upload_local_photo, get_fsm_step
from modules.profile.keyboards import (
    get_settings_keyboard, get_change_data_keyboard,
    get_reset_confirm_keyboard, get_skin_keyboard
)

async def settings_handler_logic(vk_id: int, peer_id: int, message: Message = None, skip_lock: bool = False):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        text = "✦ НАСТРОЙКИ И ЮРИДИЧЕСКИЙ ЩИТ ✦"
        kb_json = get_settings_keyboard()
        if message:
            await message.answer(text, keyboard=kb_json)
        else:
            await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb_json, random_id=0)
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def settings_change_data_logic(vk_id: int, message: Message, skip_lock: bool = False):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await set_user_state(vk_id, json.dumps({"step": "date"}))
        await message.answer("Укажите ДАТУ вашего прихода в этот мир (например, 15.04.1990):")
    finally:
        await release_lock(vk_id)

async def process_change_date_logic(vk_id: int, message: Message, skip_lock: bool = False):
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        new_date = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "time", "date": new_date}))
        await message.answer(f"Дата {new_date} принята. Теперь введите ВРЕМЯ вашего рождения (например, 14:30 или 'не знаю'):")
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def process_change_time_logic(vk_id: int, message: Message, skip_lock: bool = False):
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        new_time = message.text.strip()
        state_dict = await get_fsm_step(vk_id)
        new_date = state_dict.get("date", "")
        await set_user_state(vk_id, json.dumps({"step": "city", "date": new_date, "time": new_time}))
        await message.answer(f"Время {new_time} принято. Теперь введите ГОРОД вашего рождения:")
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def process_change_city_logic(vk_id: int, message: Message, skip_lock: bool = False):
    if not skip_lock and not await acquire_lock(vk_id): return
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

        kb_json = get_change_data_keyboard()
        await message.answer(f"Твои данные обновлены: {new_date}, {new_time}, г. {new_city}", keyboard=kb_json)
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def settings_cancel_subscription_logic(vk_id: int, message: Message, skip_lock: bool = False):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await message.answer("Ваш аккаунт не имеет активных рекуррентных подписок. Все платежи разовые. Для прекращения получения транзитов просто не пополняйте баланс. Отвязка карт не требуется по ФЗ №376-ФЗ.")
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def settings_reset_account_logic(vk_id: int, message: Message, skip_lock: bool = False):
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await set_user_state(vk_id, json.dumps({"step": "waiting_reset_confirm"}))
        kb_json = get_reset_confirm_keyboard()
        await message.answer(
            "⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс в системе. Вы уверены?",
            keyboard=kb_json
        )
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def confirm_reset_account_logic(vk_id: int, message: Message, skip_lock: bool = False):
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        await delete_user(vk_id)
        await set_user_state(vk_id, "")
        await message.answer("Система обнулена. Напишите 'Начать', чтобы заново войти в матрицу.")
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def settings_choose_character_logic(vk_id: int, peer_id: int, message: Message = None, skip_lock: bool = False):
    await set_user_state(vk_id, "")
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user:
            msg = "ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'."
            if message:
                await message.answer(msg)
            else:
                await bot.api.messages.send(peer_id=peer_id, message=msg, random_id=0)
            return

        purchased_skins = user.get("purchased_skins", [])

        styles = {
            "olesya": "сарказм", "Олеся Ивонченко": "сарказм",
            "asket": "строгость", "Серьезный Аскет": "строгость",
            "Влад Череватов": "дерзость", "Виктория Райдес": "властность",
            "Олег Шэпс": "загадочность", "Александр Шеппс": "мистицизм",
            "Баба Ванга": "пророчества", "Григорий Распутин": "безумие",
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

            is_owned = skin_name in purchased_skins or skin_name in free_skins
            kb_json = get_skin_keyboard(skin_name, is_owned)

            if photo:
                try:
                    if message:
                        await message.answer(text, attachment=photo, keyboard=kb_json)
                    else:
                        await bot.api.messages.send(peer_id=peer_id, message=text, attachment=photo, keyboard=kb_json, random_id=0)
                except Exception:
                    if message:
                        await message.answer(text, keyboard=kb_json)
                    else:
                        await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb_json, random_id=0)
            else:
                if message:
                    await message.answer(text, keyboard=kb_json)
                else:
                    await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb_json, random_id=0)
    finally:
        if not skip_lock:
            await release_lock(vk_id)

async def process_skin_action_logic(vk_id: int, message: Message, skip_lock: bool = False):
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        user = await get_user(vk_id)
        if not user:
            return

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
        if not skip_lock:
            await release_lock(vk_id)
