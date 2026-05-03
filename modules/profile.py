import asyncio
import json
import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, generate_pdf, get_fsm_step,  upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, get_storefront_keyboard, active_tasks, cover_cache

labeler = BotLabeler()

@labeler.message(text=["✦ Баланс", "Баланс", "💳 БАЛАНС"])
async def show_balance(message: Message):
    vk_id = message.from_id
    user = await get_user(vk_id)
    if not user:
        await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
        return

    balance = user.get("balance", 0)

    await message.answer(f"ТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ")

@labeler.message(text=["✦ Настройки", "Настройки", "⚙ НАСТРОЙКИ"])
async def settings_handler(message: Message):
    vk_id = message.from_id
    if vk_id in active_tasks:
        return

    user = await get_user(vk_id)
    if not user:
        await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
        return

    active_tasks.add(vk_id)
    try:
        import json
        purchased_skins = user.get("purchased_skins", [])
        active_skin = user.get("active_skin", "olesya")
        balance = user.get("balance", 0)

        free_skins = ["Олеся Ивонченко", "Серьезный Аскет"]
        paid_skins = ["Олег Шэпс", "Влад Череватов", "Виктория Райдес", "Александр Шеппс", "Баба Ванга", "Григорий Распутин"]

        await message.answer(f"✦ ВЫБОР СКИНА (ИИ-ПЕРСОНАЖА) ✦\n\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ.\nВыбери своего проводника в мир непознанного.")

        # Отправляем бесплатные скины
        for skin in free_skins:
            await asyncio.sleep(0.5)
            from modules.utils import SKIN_ASSETS
            skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(skin, "o.png"))
            if skin_att:
                await message.answer(attachment=skin_att)
                await asyncio.sleep(0.5)

            btn_color = "positive" if skin == active_skin or (skin == "Олеся Ивонченко" and active_skin == "olesya") else "secondary"
            label = f"[{skin}] - Активен" if btn_color == "positive" else skin
            payload = f"SKIN_{skin}"

            keyboard_obj = {
                "inline": True,
                "buttons": [[{"action": {"type": "text", "label": label, "payload": payload}, "color": btn_color}]]
            }
            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
            try:
                await message.answer(f"Бесплатный скин:\n{skin}", keyboard=kb_json)
            except Exception:
                await message.answer(f"Бесплатный скин:\n{skin}")

        # Отправляем платные скины
        for skin in paid_skins:
            await asyncio.sleep(0.5)
            from modules.utils import SKIN_ASSETS
            skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(skin, "o.png"))
            if skin_att:
                await message.answer(attachment=skin_att)
                await asyncio.sleep(0.5)

            if skin in purchased_skins:
                btn_color = "positive" if skin == active_skin else "secondary"
                label = f"[{skin}] - Активен" if btn_color == "positive" else skin
                payload = f"SKIN_{skin}"

                keyboard_obj = {
                    "inline": True,
                    "buttons": [[{"action": {"type": "text", "label": label, "payload": payload}, "color": btn_color}]]
                }
                kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
                try:
                    await message.answer(f"Купленный скин:\n{skin}", keyboard=kb_json)
                except Exception:
                    await message.answer(f"Купленный скин:\n{skin}")
            else:
                keyboard_obj = {
                    "inline": True,
                    "buttons": [[{"action": {"type": "text", "label": f"Купить {skin}", "payload": f"BUY_SKIN_{skin}"}, "color": "primary"}]]
                }
                kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
                try:
                    await message.answer(f"Премиум скин:\n{skin}\nЦена: 150 РУБ или 15 бонусов.", keyboard=kb_json)
                except Exception:
                    await message.answer(f"Премиум скин:\n{skin}\nЦена: 150 РУБ или 15 бонусов.")

        await asyncio.sleep(0.5)
        await message.answer("ВНИМАНИЕ: ИИ-персонажи - это цифровая пародия. Совпадения с реальными личностями - дань уважения их образу для развлекательных целей. Реальные люди не имеют отношения к ответам системы.")
    finally:
        active_tasks.discard(vk_id)

@labeler.message(func=lambda m: m.text and (m.text.startswith("SKIN_") or m.text.startswith("BUY_SKIN_") or m.text in ["Олеся Ивонченко", "Серьезный Аскет"] or any(s in m.text for s in ["Олег Шэпс", "Влад Череватов", "Виктория Райдес", "Александр Шеппс", "Баба Ванга", "Григорий Распутин"])))
async def process_skin_action(message: Message):
    vk_id = message.from_id
    if vk_id in active_tasks:
        return

    user = await get_user(vk_id)
    if not user:
        return

    active_tasks.add(vk_id)
    try:
        import json
        text = message.text

        free_skins = ["Олеся Ивонченко", "Серьезный Аскет"]
        paid_skins = ["Олег Шэпс", "Влад Череватов", "Виктория Райдес", "Александр Шеппс", "Баба Ванга", "Григорий Распутин"]

        # Парсим действие
        action = ""
        target_skin = ""

        if text.startswith("SKIN_"):
            action = "set"
            target_skin = text.replace("SKIN_", "")
        elif text.startswith("BUY_SKIN_"):
            action = "buy"
            target_skin = text.replace("BUY_SKIN_", "")
        else:
            # Обработка если кнопка вернула просто текст без payload (хотя мы отправляли payload, но для надежности)
            for s in free_skins:
                if s in text:
                    action = "set"
                    target_skin = s
                    break
            if not action:
                for s in paid_skins:
                    if f"Купить {s}" in text:
                        action = "buy"
                        target_skin = s
                        break
                    elif s in text:
                        action = "set"
                        target_skin = s
                        break

        if not action or not target_skin:
            return

        purchased_skins = user.get("purchased_skins", [])
        balance = user.get("balance", 0)

        if action == "set":
            if target_skin in free_skins or target_skin in purchased_skins:
                await update_user(vk_id, {"active_skin": target_skin})
                await message.answer(f"Скин '{target_skin}' успешно активирован. Система теперь говорит его голосом.")
            else:
                await message.answer("Этот скин недоступен. Сначала купите его.")

        elif action == "buy":
            if target_skin in purchased_skins:
                await message.answer("Этот скин уже куплен.")
                return

            if target_skin not in paid_skins:
                return

            price = 150
            bonus_price = 15
            bonuses = user.get("bonuses", 0)

            if bonuses >= bonus_price:
                new_bonuses = bonuses - bonus_price
                purchased_skins.append(target_skin)
                await update_user(vk_id, {
                    "bonuses": new_bonuses,
                    "purchased_skins": purchased_skins,
                    "active_skin": target_skin
                })
                await message.answer(f"Скин '{target_skin}' успешно приобретен и активирован!\nВаш баланс: {balance} РУБ / 💎 {new_bonuses} бонусов.")
            elif balance >= price:
                new_balance = balance - price
                purchased_skins.append(target_skin)
                await update_user(vk_id, {
                    "balance": new_balance,
                    "purchased_skins": purchased_skins,
                    "active_skin": target_skin
                })
                await message.answer(f"Скин '{target_skin}' успешно приобретен и активирован!\nВаш баланс: 💳 {new_balance} РУБ.")
            else:
                keyboard_obj = {
                    "inline": True,
                    "buttons": [[{
                        "action": {"type": "vkpay", "hash": f"action=pay-to-group&group_id=219181948&amount={price}"}
                    }]]
                }
                kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
                try:
                    await message.answer(f"Недостаточно средств для покупки '{target_skin}'. Цена: {price} РУБ или {bonus_price} бонусов.\nВаш баланс: {balance} РУБ / {bonuses} бонусов.\nПополните счет для оплаты.", keyboard=kb_json)
                except Exception:
                    await message.answer(f"Недостаточно средств для покупки '{target_skin}'. Цена: {price} РУБ или {bonus_price} бонусов.\nВаш баланс: {balance} РУБ / {bonuses} бонусов.\nПополните счет для оплаты.")
    finally:
        active_tasks.discard(vk_id)

@labeler.message(text=["✦ Мой профиль", "Мой профиль", "✦ МОЙ ПРОФИЛЬ 👤", "✦ МОЙ ПРОФИЛЬ"])
async def show_profile(message: Message):
    import json
    vk_id = message.from_id
    user = await get_user(vk_id)
    if not user:
        await message.answer("ДАННЫЕ ОТСУТСТВУЮТ. Напишите 'Начать'.")
        return

    date = user.get("birth_date", "Неизвестно")
    time = user.get("birth_time", "Неизвестно")
    city = user.get("birth_city", "Неизвестно")
    purchased = user.get("purchased_sections", {})
    first_name = purchased.get("first_name", "")

    name_line = f"👤 ИМЯ: {first_name}\n" if first_name else ""

    unlocked_count = 0
    if purchased.get("sex"): unlocked_count += 1
    if purchased.get("money"): unlocked_count += 1
    if purchased.get("shadow"): unlocked_count += 1
    if purchased.get("final"): unlocked_count += 1

    percent = unlocked_count * 25
    progress_bar = f"📊 СИНХРОНИЗАЦИЯ: {percent}%\n"

    storefront_kb = await get_storefront_keyboard(purchased)
    status_text = "" if storefront_kb else "\n\nВСЕ РАЗДЕЛЫ ОТКРЫТЫ."

    visit_streak = user.get("visit_streak", 0)
    unlocked_cards = user.get("unlocked_cards", [])
    cards_count = len(unlocked_cards)

    transit_expires = user.get("transit_sub_expires_at")
    transit_status = "Базовый"
    transit_timer = "Отсутствует"
    if transit_expires:
        import datetime
        try:
            exp_date = datetime.datetime.fromisoformat(transit_expires)
            if exp_date > datetime.datetime.now():
                transit_status = "Активен"
                transit_timer = exp_date.strftime("%d.%m.%Y")
        except ValueError:
            pass

    is_awake = "Пробужденный" if unlocked_count == 4 else "Спящий"

    profile_text = (
        f"✦ ЛИЧНЫЙ ТЕРМИНАЛ АСКЕТА ✦\n\n"
        f"{name_line}📍 ТОЧКА ВХОДА: {date} {time} {city}\n\n"
        f"⏳ ДНЕЙ В МАТРИЦЕ: {visit_streak}\n"
        f"🎴 СОБРАНО КАРТ: {cards_count}/78\n"
        f"{progress_bar}"
        f"🛡 СТАТУС: {is_awake}\n"
        f"📡 ТРАНЗИТ: {transit_status}\n"
        f"🕙 ДОСТУП ДО: {transit_timer}\n"
        f"{status_text}"
    )

    kb_dict = json.loads(await get_sections_keyboard(vk_id, user))

    # Add grimoire button
    kb_dict["buttons"].insert(0, [{"action": {"type": "text", "label": "🎴 МОЙ ГРИМУАР"}, "color": "secondary"}])

    kb_json = json.dumps(kb_dict, ensure_ascii=False)
    try:
        await message.answer(profile_text, keyboard=kb_json)
    except Exception:
        await message.answer(profile_text)

@labeler.message(text=["🎴 МОЙ ГРИМУАР"])
async def show_grimoire(message: Message):
    import json
    vk_id = message.from_id
    user = await get_user(vk_id)
    if not user:
        return

    unlocked_cards = user.get("unlocked_cards", [])

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
        unlocked_cards = {k: "Первое касание" for k in unlocked_cards}

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

    if vk_id in active_tasks:
        return

    active_tasks.add(vk_id)
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
                "ЛАЙН ПОДАЛ ГОЛОС. СИСТЕМА УЗНАЛА СВОЕГО СОЗДАТЕЛЯ. ВСЕ ОГРАНИЧЕНИЯ СНЯТЫ. ПРИЯТНОГО АНАЛИЗА, МОЙ ПОВЕЛИТЕЛЬ ИГОРЬ.",
                keyboard=kb_json
            )
        except Exception:
            await message.answer(
                "ЛАЙН ПОДАЛ ГОЛОС. СИСТЕМА УЗНАЛА СВОЕГО СОЗДАТЕЛЯ. ВСЕ ОГРАНИЧЕНИЯ СНЯТЫ. ПРИЯТНОГО АНАЛИЗА, МОЙ ПОВЕЛИТЕЛЬ ИГОРЬ."
            )
    finally:
        active_tasks.discard(vk_id)


@labeler.message(text=["Слить друга", "✦ Слить друга"])
async def referral_handler(message: Message):
    vk_id = message.from_id
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
