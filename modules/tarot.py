import asyncio
import json
import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, generate_pdf, get_fsm_step,  upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, cover_cache
from cache import acquire_lock, release_lock

labeler = BotLabeler()

async def is_waiting_oracle_cut(message: Message) -> bool:
    if message.text and message.text.lower() in ["начать", "start", "/start", "лайн голос"]:
        return False
    if message.text and message.text.startswith("✦") and "ОБРЕЗАТЬ КОЛОДУ" not in message.text:
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "oracle_cut"

@labeler.message(func=is_waiting_oracle_cut)
async def process_oracle_cut(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        import json
        import random
        state_dict = await get_fsm_step(vk_id)
        question = state_dict.get("question", "")

        pool = list(range(0, 78))
        random.shuffle(pool)
        pool = pool[:10]

        await set_user_state(vk_id, json.dumps({
            "step": "oracle_draw",
            "question": question,
            "drawn_cards": [],
            "pool": pool
        }))

        from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Callback
        kb = Keyboard(inline=True)
        for i, card_id in enumerate(pool):
            if i > 0 and i % 5 == 0:
                kb.row()
            kb.add(Callback("🎴", payload={"oracle_card": card_id}))

        await message.answer(
            "ШАГ 3 ИЗ 3: ВЫБОР КАРТ. Выбери из своей стопки ровно 3 карты",
            keyboard=kb.get_json()
        )
    finally:
        await release_lock(vk_id)

async def process_oracle_final(vk_id: int, text: str, card_ids: list):
    user = await get_user(vk_id)
    if not user:
        return

    import datetime
    import asyncio
    from ai_service import generate_text

    try:
        attachments = []
        for cid in card_ids:
            photo = await upload_local_photo(bot.api, f"{cid}.jpeg")
            if photo:
                attachments.append(photo)

        import json
        try:
            with open("tarot_ids.json", "r", encoding="utf-8") as f:
                tarot_names = json.load(f)
        except Exception:
            tarot_names = {}

        c_names = [tarot_names.get(str(cid), f"Карта {cid}") for cid in card_ids]

        # Send cards with delays
        messages = ["СЧИТЫВАЮ ПОТОК...", "ПЕРЕВОЖУ ЯЗЫК ТАРО...", "ФОРМИРУЮ ПРИГОВОР..."]
        delays = [1, 1, 2]

        for i in range(3):
            await bot.api.messages.send(
                peer_id=vk_id,
                message=messages[i],
                random_id=0
            )
            await asyncio.sleep(delays[i])

        await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
        await asyncio.sleep(4)

        from modules.utils import SKIN_ASSETS
        active_skin = user.get("active_skin", "olesya") if user else "olesya"
        skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"))
        if skin_att:
            await bot.api.messages.send(peer_id=vk_id, message="", attachment=skin_att, random_id=0)

        # Build prompt with user context
        purchased = user.get("purchased_sections", {})
        sex_val = purchased.get("sex_val", 0)
        first_name = purchased.get("first_name", "")
        gender_str = "ЖЕНЩИНА" if sex_val == 1 else "МУЖЧИНА"

        prompt = (
            f"КОНТЕКСТ: {gender_str}. "
            f"Пользователь задает вопрос: {text}. "
            f"Выпали карты: 1. {c_names[0]}, 2. {c_names[1]}, 3. {c_names[2]}. "
            "Сначала выведи: Карта [N]: [Название] - [Краткий смысл]. Только потом делай общий синтез."
        )

        result_text = await generate_text(prompt, skin=active_skin)
        if not result_text:
            result_text = "Оракул молчит. Попробуй позже."

        # Update database
        purchased["oracle_last_used"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if purchased.get("oracle_access", False):
            purchased["oracle_access"] = False # consume the pass

        user = await get_user(vk_id)
        if user:
            unlocked_cards = user.get("unlocked_cards", {})
            if not unlocked_cards or isinstance(unlocked_cards, list):
                unlocked_cards = {}

            for cid_int in card_ids:
                cid = str(cid_int)
                if cid not in unlocked_cards:
                    from ai_service import generate_text
                    grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
                    signature = await generate_text(grimoire_prompt, skin=active_skin)
                    unlocked_cards[cid] = signature if signature else "Первое касание"

            current_total = user.get("total_cards_received", 0)
            await update_user(vk_id, {"purchased_sections": purchased, "total_cards_received": current_total + 3, "unlocked_cards": unlocked_cards})
        else:
            await update_user(vk_id, {"purchased_sections": purchased})

        kb_json = await get_sections_keyboard(vk_id, user)

        try:
            await bot.api.messages.send(
                peer_id=vk_id,
                message=result_text,
                keyboard=kb_json,
                random_id=0
            )
        except Exception:
            await bot.api.messages.send(
                peer_id=vk_id,
                message=result_text,
                random_id=0
            )

        for att in attachments:
            await bot.api.messages.send(peer_id=vk_id, message="", attachment=att, random_id=0)
            await asyncio.sleep(0.5)

    except Exception as e:
        print(f"Error in process_oracle_final: {e}")

@labeler.message(text=["Карта дня", "✦ Карта дня", "🃏 КАРТА ДНЯ"])
async def card_of_day_handler(message: Message):
    import json
    import datetime
    import re
    import random
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
        await release_lock(vk_id)
        return

    text = message.text.strip()
    if not text or text.lower() in ["начать", "start", "/start", "лайн голос"] or (text.startswith("✦") and "Карта дня" not in text):
        await release_lock(vk_id)
        return

    state_dict = await get_fsm_step(vk_id)
    if state_dict is not None and "step" in state_dict:
        await release_lock(vk_id)
        return

    try:
        purchased = user.get("purchased_sections", {})
        last_used_str = purchased.get("card_of_day_last_used")
        allow_access = False

        if not last_used_str:
            allow_access = True
        else:
            try:
                last_time = datetime.datetime.fromisoformat(last_used_str)
                if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() >= 24 * 3600:
                    allow_access = True
            except ValueError:
                allow_access = True

        if not allow_access:
            keyboard_obj = {
                "inline": True,
                "buttons": [[{
                    "action": {"type": "text", "label": "ВОПРОС СУДЬБЕ"}, "color": "primary"
                }]]
            }
            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
            try:
                await message.answer(
                    "Твой лимит на сегодня исчерпан. Карта дня на то и карта дня что выдается один раз в день. Потоки энергии требуют времени для восстановления. Если тебе нужен срочный ответ, обратись к Оракулу.",
                    keyboard=kb_json
                )
            except Exception:
                await message.answer(
                    "Твой лимит на сегодня исчерпан. Карта дня на то и карта дня что выдается один раз в день. Потоки энергии требуют времени для восстановления. Если тебе нужен срочный ответ, обратись к Оракулу."
                )
            return

        await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
        await message.answer("Тяну карту дня...")
        import asyncio
        await asyncio.sleep(2)

        # Update streak
        visit_streak = user.get("visit_streak", 0)
        weekly_log = user.get("weekly_log", [])
        unlocked_cards = user.get("unlocked_cards", [])

        last_used_str = purchased.get("card_of_day_last_used")
        if last_used_str:
            try:
                last_time = datetime.datetime.fromisoformat(last_used_str)
                if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() > 48 * 3600:
                    visit_streak = 1
                    weekly_log = []
                else:
                    visit_streak += 1
            except ValueError:
                visit_streak = 1
                weekly_log = []
        else:
            visit_streak = 1
            weekly_log = []

        # Mark used
        purchased["card_of_day_last_used"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        date = user.get("birth_date", "неизвестно")
        time = user.get("birth_time", "неизвестно")
        city = user.get("birth_city", "неизвестно")
        first_name = purchased.get("first_name", "")
        sex_val = purchased.get("sex_val", 0)
        core_profile = user.get("core_profile", "")

        from ai_service import generate_section
        active_skin = user.get("active_skin", "olesya") if user else "olesya"
        result_text = await generate_section("card_of_day", date, time, city, core_profile, first_name, sex_val, skin=active_skin)

        if not result_text:
            result_text = "Энергетический сбой. Не удалось вытянуть карту."

        if first_name:
            result_text = f"{first_name},\n\n" + result_text

        kb_json = await get_sections_keyboard(vk_id, user)

        match = re.search(r"ID_?ТАРО:\s*(\d+)", result_text)
        if match:
            num = int(match.group(1))
            if 0 <= num <= 77:
                card_id = str(num)
            else:
                card_id = str(random.randint(0, 77))
        else:
            card_id = str(random.randint(0, 77))

        if not unlocked_cards or isinstance(unlocked_cards, list):
            unlocked_cards = {}

        if card_id not in unlocked_cards:
            from ai_service import generate_text
            grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
            signature = await generate_text(grimoire_prompt, skin=active_skin)
            unlocked_cards[card_id] = signature if signature else "Первое касание"

        weekly_log.append(card_id)

        # Increment total_cards_received and save updates
        user = await get_user(vk_id)
        if user:
            current_total = user.get("total_cards_received", 0)
            await update_user(vk_id, {
                "total_cards_received": current_total + 1,
                "purchased_sections": purchased,
                "unlocked_cards": unlocked_cards,
                "weekly_log": weekly_log,
                "visit_streak": visit_streak
            })

        photo_attachment = None
        try:
            from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  PhotoMessageUploader
            photo_attachment = await upload_local_photo(bot.api, f"{card_id}.jpeg")
        except Exception as e:
            print(f"Failed to upload tarot card {card_id}: {e}")

        display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", result_text).strip()

        parts = re.split(rf"(?i)\bКАРТА ДНЯ\b", display_text, maxsplit=1)
        intro = ""
        main_part = display_text

        if len(parts) > 1:
            intro = parts[0].strip()
            main_part = f"КАРТА ДНЯ\n" + parts[1].strip()

        from modules.utils import SKIN_ASSETS
        skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"))
        if skin_att:
            await message.answer(attachment=skin_att)
            await asyncio.sleep(0.5)

        if intro:
            await message.answer(intro)
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")
            await asyncio.sleep(4)
            try:
                await message.answer(main_part, keyboard=kb_json)
            except Exception:
                await message.answer(main_part)
        else:
            try:
                await message.answer(display_text, keyboard=kb_json)
            except Exception:
                await message.answer(display_text)

        if photo_attachment:
            # Пытаемся достать значение карты из Гримуара, чтобы сделать подпись
            caption = ""
            if user:
                unlocked_cards = user.get("unlocked_cards", {})
                if isinstance(unlocked_cards, dict):
                    caption = unlocked_cards.get(card_id, "Новая карта добавлена в твой Гримуар.")

            try:
                await message.answer(f"🎴 Значение карты:\n{caption}", attachment=photo_attachment)
            except Exception:
                await message.answer("", attachment=photo_attachment)

        if visit_streak >= 7:
            await asyncio.sleep(2)
            await message.answer("Твоя недельная матрица синхронизирована. Твой бесплатный отчет готов.")
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")
            await asyncio.sleep(3)

            try:
                with open("tarot_ids.json", "r", encoding="utf-8") as f:
                    tarot_names = json.load(f)
            except Exception:
                tarot_names = {}

            w_names = [tarot_names.get(str(cid), f"Карта {cid}") for cid in weekly_log[-7:]]

            synthesis_prompt = (
                f"Это еженедельный отчет. За неделю выпали карты: {', '.join(w_names)}. "
                "Проанализируй этот список в динамике, сделай профессиональный разбор. "
                "Что преобладало, какие тенденции, и куда это ведет."
            )

            synthesis_result = await generate_text(synthesis_prompt, skin=active_skin)
            if synthesis_result:
                await message.answer(f"✦ ЕЖЕНЕДЕЛЬНЫЙ СИНТЕЗ ✦\n\n{synthesis_result}")

            await update_user(vk_id, {
                "visit_streak": 0,
                "weekly_log": []
            })

    finally:
        await release_lock(vk_id)

@labeler.message(text=["ВОПРОС СУДЬБЕ", "✦ ВОПРОС СУДЬБЕ"])
async def oracle_handler(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
        await release_lock(vk_id)
        return

    # Игнорируем команды и системные сообщения
    text = message.text.strip()
    if not text or text.lower() in ["начать", "start", "/start", "лайн голос"] or text.startswith("✦"):
        await release_lock(vk_id)
        return

    # Проверяем, не в FSM ли мы
    state_dict = await get_fsm_step(vk_id)
    if state_dict is not None and "step" in state_dict:
        await release_lock(vk_id)
        return

    try:
        import datetime
        import json

        purchased = user.get("purchased_sections", {})
        oracle_last_used_str = purchased.get("oracle_last_used")
        has_paid_access = purchased.get("oracle_access", False)

        allow_access = False
        if has_paid_access:
            allow_access = True
        else:
            if not oracle_last_used_str:
                allow_access = True
            else:
                try:
                    last_time = datetime.datetime.fromisoformat(oracle_last_used_str)
                    if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() >= 24 * 3600:
                        allow_access = True
                except ValueError:
                    allow_access = True

        if not allow_access:
            last_time = datetime.datetime.fromisoformat(oracle_last_used_str)
            remaining = datetime.timedelta(hours=24) - (datetime.datetime.now(datetime.timezone.utc) - last_time)
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            balance = user.get("balance", 0)

            if balance >= 50:
                keyboard_obj = {
                    "inline": True,
                    "buttons": [[{
                        "action": {"type": "text", "label": "ВОПРОС СУДЬБЕ"}, "color": "secondary"
                    }]]
                }
                kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
                try:
                    await message.answer(
                        f"СИСТЕМА ПЕРЕГРЕТА. Твое будущее на сегодня исчерпано. Приходи завтра или оплати принудительную синхронизацию.\nЭнергия восстанавливается. Осталось {hours} ч. {minutes} мин.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ. Пропустить таймер: 50 РУБ.",
                        keyboard=kb_json
                    )
                except Exception:
                    await message.answer(
                        f"СИСТЕМА ПЕРЕГРЕТА. Твое будущее на сегодня исчерпано. Приходи завтра или оплати принудительную синхронизацию.\nЭнергия восстанавливается. Осталось {hours} ч. {minutes} мин.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ. Пропустить таймер: 50 РУБ."
                    )
            else:
                keyboard_obj = {
                    "inline": True,
                    "buttons": [[{
                        "action": {"type": "vkpay", "hash": "action=pay-to-group&group_id=219181948&amount=50"}
                    }]]
                }
                kb_json = json.dumps(keyboard_obj, ensure_ascii=False)

                try:
                    await message.answer(
                        f"СИСТЕМА ПЕРЕГРЕТА. Твое будущее на сегодня исчерпано. Приходи завтра или оплати принудительную синхронизацию.\nЭнергия восстанавливается. Осталось {hours} ч. {minutes} мин.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ.",
                        keyboard=kb_json
                    )
                except Exception:
                    await message.answer(
                        f"СИСТЕМА ПЕРЕГРЕТА. Твое будущее на сегодня исчерпано. Приходи завтра или оплати принудительную синхронизацию.\nЭнергия восстанавливается. Осталось {hours} ч. {minutes} мин.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ."
                    )
            return

        # Start Oracle FSM
        await set_user_state(vk_id, json.dumps({"step": "waiting_oracle_question"}))

        await message.answer("ШАГ 1 ИЗ 3: ТВОЙ ВОПРОС. Напиши, что тебя волнует?\nСформулируй вопрос максимально конкретно. Система не любит размытых мыслей.")

    finally:
        await release_lock(vk_id)

async def is_waiting_oracle_question(message: Message) -> bool:
    if message.text and message.text.startswith("✦"):
        return False
    if message.text and message.text.lower() in ["начать", "start", "/start", "лайн голос"]:
        return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_oracle_question"

@labeler.message(func=is_waiting_oracle_question)
async def process_oracle_question(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        import json
        text = message.text.strip()
        await set_user_state(vk_id, json.dumps({"step": "oracle_cut", "question": text}))
        from vkbottle import Keyboard, KeyboardButtonColor, Text
        kb = Keyboard(inline=True)
        kb.add(Text("✦ ОБРЕЗАТЬ КОЛОДУ"), color=KeyboardButtonColor.PRIMARY)
        try:
            await message.answer(
                "ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Вопрос принят. Жми кнопку ниже, чтобы обрезать колоду",
                keyboard=kb.get_json()
            )
        except Exception:
            await message.answer("ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Вопрос принят. Жми кнопку ниже, чтобы обрезать колоду")
    finally:
        await release_lock(vk_id)


@labeler.message(text=["АНТИТАРО", "✦ АНТИТАРО", "👺 АНТИТАРО"])
async def antitarot_handler(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
        await release_lock(vk_id)
        return

    balance = user.get("balance", 0)
    if balance < 50:
        await message.answer("ДЛЯ АКТИВАЦИИ АНТИТАРО НУЖНО 50 РУБ. ТВОЙ БАЛАНС НЕДОСТАТОЧЕН.", keyboard=get_dynamic_keyboard(user))
        await release_lock(vk_id)
        return

    try:
        await message.answer("Активирую темный канал...", keyboard=Keyboard(inline=True).get_json())
        await bot.api.messages.set_activity(peer_id=vk_id, type="typing")

        # Deduct balance
        new_balance = balance - 50
        await update_user(vk_id, {"balance": new_balance})

        prompt = "Сделай анти-разбор таро, максимально циничный, деструктивный и жесткий совет наоборот."
        result = await generate_text(prompt, skin=user.get("active_skin", "olesya"))

        # Upload dark cover or random
        att = await upload_local_photo(bot.api, "cover_dark.jpeg")

        await message.answer(f"✦ АНТИТАРО ✦\n\n{result}", attachment=att, keyboard=get_dynamic_keyboard(user))
    finally:
        await release_lock(vk_id)
