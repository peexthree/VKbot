from cache import acquire_lock, release_lock
from modules.states import MyStates
import asyncio
import json
import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader, Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, get_fsm_step, upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, cover_cache
from loguru import logger

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

        from vkbottle import Callback
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
    logger.info(f"process_oracle_final triggered by vk_id={vk_id}")
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

        from cache import get_tarot_names
        tarot_names = await get_tarot_names()

        c_names = [tarot_names.get(str(cid), f"Карта {cid}") for cid in card_ids]

        messages = ["Настраиваюсь на вашу энергию...", "Раскладываю карты...", "Формирую ваш ответ..."]
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

        purchased = user.get("purchased_sections", {})
        sex_val = purchased.get("sex_val", 0)
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

        purchased["oracle_last_used"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if purchased.get("oracle_access", False):
            purchased["oracle_access"] = False

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
        except Exception as e:
            await bot.api.messages.send(
                peer_id=vk_id,
                message=result_text,
                random_id=0
            )

        for att in attachments:
            await bot.api.messages.send(peer_id=vk_id, message="", attachment=att, random_id=0)
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.exception(f"Error in process_oracle_final: {e}")

@labeler.message(text=["Карта дня", "✦ Карта дня", "🃏 Карта дня"])
async def card_of_day_handler(message: Message):
    import json
    import datetime
    import re
    import random
    vk_id = message.from_id
    logger.info(f"card_of_day_handler triggered by vk_id={vk_id}")
    from database import set_user_state
    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
        return

    text = message.text.strip()
    if not text or text.lower() in ["начать", "start", "/start", "лайн голос"] or (text.startswith("✦") and "Карта дня" not in text):
        return

    state_dict = await get_fsm_step(vk_id)
    if state_dict is not None and "step" in state_dict:
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
                    "action": {"type": "callback", "payload": json.dumps({"cmd": "buy", "type": "service", "key": "oracle"}), "label": "ВОПРОС СУДЬБЕ (ОРАКУЛ)"}, "color": "primary"
                }]]
            }
            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
            try:
                await message.answer(
                    "Твой лимит на сегодня исчерпан. Карта дня на то и карта дня что выдается один раз в день. Потоки энергии требуют времени для восстановления. Если тебе нужен срочный ответ, обратись к Оракулу.",
                    keyboard=kb_json
                )
            except Exception as e:
                await message.answer(
                    "Твой лимит на сегодня исчерпан. Карта дня на то и карта дня что выдается один раз в день. Потоки энергии требуют времени для восстановления. Если тебе нужен срочный ответ, обратись к Оракулу."
                )
            return

        await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
        await message.answer("Тяну карту дня...")
        import asyncio
        await asyncio.sleep(2)

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
            from vkbottle import PhotoMessageUploader
            photo_attachment = await upload_local_photo(bot.api, f"{card_id}.jpeg")
        except Exception as e:
            logger.exception(f"Failed to upload tarot card {card_id}: {e}")

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
            except Exception as e:
                await message.answer(main_part)
        else:
            try:
                await message.answer(display_text, keyboard=kb_json)
            except Exception as e:
                await message.answer(display_text)

        if photo_attachment:
            caption = ""
            if user:
                unlocked_cards = user.get("unlocked_cards", {})
                if isinstance(unlocked_cards, dict):
                    caption = unlocked_cards.get(card_id, "Новая карта добавлена в твой Гримуар.")

            try:
                await message.answer(f"🎴 Значение карты:\n{caption}", attachment=photo_attachment)
            except Exception as e:
                await message.answer("", attachment=photo_attachment)

        if visit_streak >= 7:
            await asyncio.sleep(2)
            await message.answer("Твоя недельная матрица синхронизирована. Твой бесплатный отчет готов.")
            await bot.api.messages.set_activity(peer_id=message.peer_id, type="typing")
            await asyncio.sleep(3)

            from cache import get_tarot_names
            tarot_names = await get_tarot_names()

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

@labeler.message(state=MyStates.WAITING_ORACLE_QUESTION)
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
        except Exception as e:
            await message.answer("ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Вопрос принят. Жми кнопку ниже, чтобы обрезать колоду")
    finally:
        await release_lock(vk_id)


