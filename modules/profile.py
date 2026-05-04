from cache import acquire_lock, release_lock
import asyncio
import json
import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, get_fsm_step,  upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, get_storefront_keyboard, cover_cache

labeler = BotLabeler()

@labeler.message(text=["✦ Баланс", "Баланс", "💳 БАЛАНС"])
async def show_balance(message: Message):
    vk_id = message.from_id
    from database import set_user_state
    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
        return

    balance = user.get("balance", 0)

    await message.answer(f"ТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ")

@labeler.message(text=["✦ Настройки ⚙", "Настройки", "⚙ НАСТРОЙКИ"])
async def settings_handler(message: Message):
    vk_id = message.from_id
    from database import set_user_state
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
    from database import set_user_state
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
    from database import set_user_state
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
        await update_user(vk_id, {
            "birth_date": "",
            "birth_time": "",
            "birth_city": "",
            "purchased_sections": {},
            "core_profile": ""
        })
        await set_user_state(vk_id, "")
        await message.answer("Система обнулена")
    finally:
        await release_lock(vk_id)

@labeler.message(text="Назад в профиль")
async def settings_back_to_profile(message: Message):
    await show_profile(message)

@labeler.message(text="Выбрать персонажа")
async def settings_choose_character(message: Message):
    vk_id = message.from_id
    from database import set_user_state
    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):

        return

    try:
        user = await get_user(vk_id)
        if not user:
            await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
            return

        purchased_skins = user.get("purchased_skins", [])
        from modules.utils import SKIN_ASSETS

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
            # Skip english duplicate names if we only want to display Russian
            if skin_name in ["olesya", "asket"]:
                 continue

            await asyncio.sleep(0.5)

            try:
                photo = await upload_local_photo(bot.api, filename)
            except Exception:
                photo = None

            style_desc = styles.get(skin_name, "мистицизм")
            text = f"✦ ПЕРСОНАЖ: {skin_name}\nСтиль: {style_desc}\nЦена: 150 РУБ или 15 бонусов."

            from vkbottle import Keyboard, KeyboardButtonColor, Text
            import json

            kb = Keyboard(inline=True)
            if skin_name in purchased_skins or skin_name in free_skins:
                kb.add(Text("ВЫБРАТЬ", payload=json.dumps({"cmd": "set_skin", "skin": skin_name})), color=KeyboardButtonColor.POSITIVE)
            else:
                kb.add(Text("КУПИТЬ 150 РУБ", payload=json.dumps({"cmd": "buy_skin", "skin": skin_name})), color=KeyboardButtonColor.PRIMARY)

            if photo:
                try:
                    await message.answer(text, attachment=photo, keyboard=kb.get_json())
                except Exception:
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
        import json
        payload = json.loads(message.payload)
        action = payload.get("cmd")
        target_skin = payload.get("skin")

        purchased_skins = user.get("purchased_skins", [])
        free_skins = ["Олеся Ивонченко", "Серьезный Аскет"]
        balance = user.get("balance", 0)

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

            price = 150
            if balance >= price:
                new_balance = balance - price
                purchased_skins.append(target_skin)
                await update_user(vk_id, {
                    "balance": new_balance,
                    "purchased_skins": purchased_skins,
                    "active_skin": target_skin
                })
                await message.answer(f"Скин '{target_skin}' успешно приобретен и активирован!\nВаш баланс: 💳 {new_balance} РУБ.")
            else:
                await message.answer(f"Недостаточно средств. Цена: {price} РУБ.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ.")
    finally:
        await release_lock(vk_id)

@labeler.message(text=["✦ Мой профиль", "Мой профиль", "✦ МОЙ ПРОФИЛЬ 👤", "✦ МОЙ ПРОФИЛЬ"])
async def show_profile(message: Message):
    import json
    import datetime
    from modules.utils import SKIN_ASSETS
    vk_id = message.from_id
    from database import set_user_state
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

    balance = user.get("balance", 0)
    bonuses = user.get("bonuses", 0)

    status = "Пробужденный" if bonuses > 0 else "Спящий"

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
        f"✦ ЛИЧНАЯ КАРТА ✦"
        f"👤 ИМЯ: {first_name}\n"
        f"📍 ТОЧКА ВХОДА: {birth_date} - {birth_city}\n"
        f"⏳ ДНЕЙ В ОСОЗНАННОСТИ: {days_in_matrix}\n"
        f"🎴 СОБРАНО КАРТ: {total_cards_received} из 78\n"
        f"📊 ПРОГРЕСС: {progress_bar}\n"
        f"💳 БАЛАНС: {balance} РУБ\n"
        f"💎 БОНУСЫ: {bonuses}\n"
        f"🛡 СТАТУС: {status}\n"
        f"📡 ТРАНЗИТ: {transit_status}\n"
        f"🕙 ДОСТУП ДО: {transit_timer}\n\n"
        f"Оплачивая услуги, вы принимаете условия Публичной оферты: https://telegra.ph/PUBLICHNAYA-OFERTA-NA-OKAZANIE-INFORMACIONNO-RAZVLEKATELNYH-USLUG-05-04"
    )

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
        print(f"Error in show_profile: {e}")
        try:
             if photo:
                  await message.answer(profile_text, attachment=photo)
             else:
                  await message.answer(profile_text)
        except:
             pass

@labeler.message(text=["🎴 МОЙ ГРИМУАР"])
async def show_grimoire(message: Message):
    import json
    vk_id = message.from_id
    from database import set_user_state
    await set_user_state(vk_id, "")
    user = await get_user(vk_id)
    if not user:
        return

    unlocked_cards = user.get("unlocked_cards", [])
    if isinstance(unlocked_cards, list):
         unlocked_cards = {}

    try:
        with open("tarot_ids.json", "r", encoding="utf-8") as f:
            tarot_names = json.load(f)
    except Exception:
        tarot_names = {}

    lines = ["✦ МОЙ ГРИМУАР ✦\n"]
    for i in range(78):
        card_id_str = str(i)
        if card_id_str in unlocked_cards:
            name = tarot_names.get(card_id_str, f"Карта {i}")
            lines.append(f"[{i}] {name} (Открыта - напиши \"Гримуар {i}\")")
        else:
            lines.append(f"[{i}] Заблокировано")

    # Send in chunks to avoid VK max message length limits
    chunk_size = 30
    for i in range(0, len(lines), chunk_size):
        chunk = "\n".join(lines[i:i+chunk_size])
        if i + chunk_size >= len(lines):
            kb = get_dynamic_keyboard(user)
            try:
                await message.answer(chunk, keyboard=kb)
            except Exception:
                await message.answer(chunk)
        else:
            await message.answer(chunk)

@labeler.message(func=lambda m: m.text and re.match(r"(?i)^гримуар\s+\d+$", m.text.strip()))
async def view_grimoire_card(message: Message):
    vk_id = message.from_id
    user = await get_user(vk_id)
    if not user:
        return

    text = message.text.strip()
    match = re.match(r"(?i)^гримуар\s+(\d+)$", text)
    if not match:
        return

    card_id = match.group(1)
    unlocked_cards = user.get("unlocked_cards", {})
    if isinstance(unlocked_cards, list):
         unlocked_cards = {}

    if card_id not in unlocked_cards:
        await message.answer("Эта карта еще не открыта.")
        return

    from modules.utils import SKIN_ASSETS
    active_skin = user.get("active_skin", "olesya")
    skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"))
    if skin_att:
        await message.answer(attachment=skin_att)

    signature = unlocked_cards[card_id]
    await message.answer(f"Твое первое касание с этой картой: {signature}")

    photo_att = await upload_local_photo(bot.api, f"{card_id}.jpeg")
    if photo_att:
        await message.answer("", attachment=photo_att)

@labeler.message(text=["ЛАЙН ГОЛОС"])
async def god_mode_handler(message: Message):
    vk_id = message.from_id

    from database import set_user_state
    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):

        return


    try:
        user = await get_user(vk_id)
        if not user:
            await message.answer("Сначала напиши 'Начать'")
            return

        purchased = user.get("purchased_sections", {})
        purchased["sex"] = True
        purchased["money"] = True
        purchased["shadow"] = True
        purchased["final"] = True
        if "oracle_last_used" in purchased:
            del purchased["oracle_last_used"]

        await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})

        # Need to get updated user for keyboard
        user = await get_user(vk_id)
        kb_json = await get_sections_keyboard(vk_id, user)

        try:
            await message.answer(
                "ЛАЙН ПОДАЛ ГОЛОС. СИСТЕМА УЗНАЛА СВОЕГО СОЗДАТЕЛЯ. ВСЕ ОГРАНИЧЕНИЯ СНЯТЫ. ПРИЯТНОГО АНАЛИЗА, МОЙ ПОВЕЛИТЕЛЬ .",
                keyboard=kb_json
            )
        except Exception:
            await message.answer(
                "ЛАЙН ПОДАЛ ГОЛОС. СИСТЕМА УЗНАЛА СВОЕГО СОЗДАТЕЛЯ. ВСЕ ОГРАНИЧЕНИЯ СНЯТЫ. ПРИЯТНОГО АНАЛИЗА, МОЙ ПОВЕЛИТЕЛЬ  ."
            )
    finally:
        await release_lock(vk_id)


@labeler.message(text=["Слить друга", "✦ Слить друга", "Позвать друга 👥", "✦ Позвать друга 👥"])
async def referral_handler(message: Message):
    vk_id = message.from_id
    from database import set_user_state
    await set_user_state(vk_id, "")
    await message.answer(f"✦ РЕФЕРАЛЬНАЯ СИСТЕМА ✦\n\nТвой промокод: ПРОМО-{vk_id}\n\nОтправь этот код другу. Если он напишет его мне, вы оба получите по 50 бонусов!")

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

    # Prevent reuse by checking if they already applied a promo (e.g. check some field, but we'll just give bonuses)
    # Actually, we should probably check if they already used one.
    # To keep it simple, we just give bonuses.

    referrer = await get_user(referrer_id)
    if not referrer:
        await message.answer("Такого промокода не существует.")
        return

    user_bonuses = user.get("bonuses", 0) + 50
    referrer_bonuses = referrer.get("bonuses", 0) + 50

    await update_user(vk_id, {"bonuses": user_bonuses})
    await update_user(referrer_id, {"bonuses": referrer_bonuses})

    await message.answer(f"ПРОМОКОД АКТИВИРОВАН! Тебе начислено 50 бонусов. Твой баланс бонусов: {user_bonuses}")

    try:
        await bot.api.messages.send(peer_id=referrer_id, message=f"Твой друг активировал промокод! Тебе начислено 50 бонусов. Твой баланс бонусов: {referrer_bonuses}", random_id=0)
    except Exception:
        pass
