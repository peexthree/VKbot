from modules.bot_init import bot
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
from modules.utils import get_fsm_step, upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, cover_cache
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
            photo = await upload_local_photo(bot.api, f"{cid}.jpeg", peer_id=vk_id)
            if photo:
                attachments.append(photo)

        tarot_names = await get_tarot_names()

        c_names = [tarot_names.get(str(cid), f"Карта {cid}") for cid in card_ids]

        from modules.utils import start_dynamic_typing
        typing_task = await start_dynamic_typing(vk_id, bot.api)

        active_skin = user.get("active_skin", "olesya") if user else "olesya"
        skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=vk_id)
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

        try:
            result_text = await generate_text(prompt, skin=active_skin)
        finally:
            typing_task.cancel()
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
                    grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."

                    await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
                    signature = await generate_text(grimoire_prompt, skin=active_skin)
                    unlocked_cards[cid] = signature if signature else "Первое касание"

            current_total = user.get("total_cards_received", 0)
            await update_user(vk_id, {"purchased_sections": purchased, "total_cards_received": current_total + 3, "unlocked_cards": unlocked_cards})
            major_arcana = [str(i) for i in range(22)]
            if all(arc in unlocked_cards for arc in major_arcana):
                purchased_skins = user.get("purchased_skins", [])
                if "Магистр" not in purchased_skins:
                    purchased_skins.append("Магистр")
                    await update_user(vk_id, {"purchased_skins": purchased_skins})
                    try:
                        await bot.api.messages.send(
                            peer_id=vk_id,
                            message="👁‍🗨 ИНИЦИАЦИЯ ПРОЙДЕНА 👁‍🗨\n\nТы собрал все 22 Старших Аркана в своем Гримуаре. Тебе открыт уникальный аватар-проводник: МАГИСТР.\n\nЗайди в Мой профиль -> Настройки -> Выбрать персонажа.",
                            random_id=0
                        )
                    except Exception:
                        pass
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
        logger.error(f"Ошибка: {str(e)}")

@labeler.message(text=["Карта дня", "✦ Карта дня", "🃏 Карта дня", "🃏 КАРТА ДНЯ"])
async def card_of_day_handler(message: Message):
    text = message.text.strip()
    if not text or text.lower() in ["начать", "start", "/start", "лайн голос"] or (text.startswith("✦") and "Карта дня" not in text):
        return
    await card_of_day_logic(message.from_id, message.peer_id)

async def card_of_day_logic(vk_id: int, peer_id: int):
    import json
    import datetime
    import re
    import random
    logger.info(f"card_of_day_logic triggered by vk_id={vk_id}")
    from database import set_user_state
    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
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
                await bot.api.messages.send(
                    peer_id=peer_id,
                    random_id=0,
                    message="Твой лимит на сегодня исчерпан. Карта дня на то и карта дня что выдается один раз в день. Потоки энергии требуют времени для восстановления. Если тебе нужен срочный ответ, обратись к Оракулу.",
                    keyboard=kb_json
                )
            except Exception as e:
                await bot.api.messages.send(
                    peer_id=peer_id,
                    random_id=0,
                    message="Твой лимит на сегодня исчерпан. Карта дня на то и карта дня что выдается один раз в день. Потоки энергии требуют времени для восстановления. Если тебе нужен срочный ответ, обратись к Оракулу."
                )
            return

        from modules.utils import start_dynamic_typing
        typing_task_cod = await start_dynamic_typing(peer_id, bot.api)

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

        from ai_service import generate_section, generate_text, extract_tags
        active_skin = user.get("active_skin", "olesya") if user else "olesya"
        tags = user.get("tags", [])

        card_id = str(random.randint(0, 77))

        if not unlocked_cards or isinstance(unlocked_cards, list):
            unlocked_cards = {}

        if card_id not in unlocked_cards:
            unlocked_cards[card_id] = "Первое касание"

        weekly_log.append(card_id)

        user = await get_user(vk_id)
        if user:
            current_total = user.get("total_cards_received", 0)
            balance = user.get("balance", 0)
            await update_user(vk_id, {
                "total_cards_received": current_total + 1,
                "purchased_sections": purchased,
                "unlocked_cards": unlocked_cards,
                "weekly_log": weekly_log,
                "visit_streak": visit_streak,
                "balance": balance + 100
            })

        photo_attachment = None
        try:
            from vkbottle import PhotoMessageUploader
            photo_attachment = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)
        except Exception as e:
            logger.error(f"Ошибка: {str(e)}")

        tarot_names = await get_tarot_names()
        card_name = tarot_names.get(card_id, f"Карта {card_id}")

        await bot.api.messages.send(peer_id=peer_id, random_id=0, message=f"Твоя карта на сегодня: {card_name}", attachment=photo_attachment)

        skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=vk_id)
        if skin_att:
            await bot.api.messages.send(peer_id=peer_id, random_id=0, message="", attachment=skin_att)


        await bot.api.messages.set_activity(peer_id=peer_id, type="typing")

        try:
            result_text = await generate_section("card_of_day", date, time, city, core_profile, first_name, sex_val, skin=active_skin, card_id=card_id, tags=tags)
        finally:
            typing_task_cod.cancel()

        async def extract_and_save_tags(vk_id: int, text: str):
            new_tags = await extract_tags(text)
            if new_tags:
                await update_user(vk_id, {"tags": new_tags})

        asyncio.create_task(extract_and_save_tags(vk_id, result_text))

        kb_json = await get_sections_keyboard(vk_id, user)

        if not result_text:
            result_text = "🔮 Произошла ошибка на стороне Оракула при вытягивании карты. Серверы перегружены, пожалуйста, попробуй позже."
            try:
                await bot.api.messages.send(peer_id=peer_id, random_id=0, message=result_text, keyboard=kb_json)
            except Exception:
                pass
            return

        if card_id in unlocked_cards and unlocked_cards[card_id] == "Первое касание":
            grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
            signature = await generate_text(grimoire_prompt, skin=active_skin)
            if signature:
                unlocked_cards[card_id] = signature
                await update_user(vk_id, {"unlocked_cards": unlocked_cards})

        user = await get_user(vk_id)
        if user:
            major_arcana = [str(i) for i in range(22)]
            unlocked = user.get("unlocked_cards", {})
            if isinstance(unlocked, dict) and all(arc in unlocked for arc in major_arcana):
                purchased_skins = user.get("purchased_skins", [])
                if "Магистр" not in purchased_skins:
                    purchased_skins.append("Магистр")
                    await update_user(vk_id, {"purchased_skins": purchased_skins})
                    try:
                        await bot.api.messages.send(
                            peer_id=peer_id,
                            message="👁‍🗨 ИНИЦИАЦИЯ ПРОЙДЕНА 👁‍🗨\n\nТы собрал все 22 Старших Аркана в своем Гримуаре. Тебе открыт уникальный аватар-проводник: МАГИСТР.\n\nЗайди в Мой профиль -> Настройки -> Выбрать персонажа.",
                            random_id=0
                        )
                    except Exception:
                        pass

        if first_name:
            result_text = f"{first_name},\n\n" + result_text

        display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", result_text).strip()

        # Add streak reward text
        streak_msg = f"\n\n> ⚡ Ритуал завершен. Тебе начислено +100 Энергии звезд за визит.\nВозвращайся завтра."
        if visit_streak < 7:
            streak_msg += f" (Серия: {visit_streak}/7. Заходи 7 дней подряд для бесплатного синтез-разбора недели)."
        display_text += streak_msg

        parts = re.split(rf"(?i)\bКАРТА ДНЯ\b", display_text, maxsplit=1)
        intro = ""
        main_part = display_text

        if len(parts) > 1:
            intro = parts[0].strip()
            main_part = f"КАРТА ДНЯ\n" + parts[1].strip()

        final_keyboard = kb_json

        user_after_update = await get_user(vk_id)
        if user_after_update and user_after_update.get("total_cards_received", 0) == 1:
            main_part += "\n\nЭта карта — твой первый цифровой отпечаток. Я занесла её в твой личный Гримуар. Там она будет копить силу."
            kb = Keyboard(inline=True)
            kb.add(Callback("📖 ОТКРЫТЬ ГРИМУАР", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.POSITIVE)
            final_keyboard = kb.get_json()

        if intro:
            await bot.api.messages.send(peer_id=peer_id, random_id=0, message=intro)
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")
            await asyncio.sleep(4)
            try:
                await bot.api.messages.send(peer_id=peer_id, random_id=0, message=main_part, keyboard=final_keyboard)
            except Exception as e:
                await bot.api.messages.send(peer_id=peer_id, random_id=0, message=main_part)
        else:
            try:
                await bot.api.messages.send(peer_id=peer_id, random_id=0, message=display_text, keyboard=final_keyboard)
            except Exception as e:
                await bot.api.messages.send(peer_id=peer_id, random_id=0, message=display_text)

        if visit_streak >= 7:
            await asyncio.sleep(2)
            await bot.api.messages.send(peer_id=peer_id, random_id=0, message="Твоя недельная матрица синхронизирована. Твой бесплатный отчет готов.")
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")
            await asyncio.sleep(3)

            from cache import get_tarot_names
            tarot_names = await get_tarot_names()

            w_names = [tarot_names.get(str(cid), f"Карта {cid}") for cid in weekly_log[-7:]]

            synthesis_prompt = (
                f"Это еженедельный отчет. За неделю выпали карты: {', '.join(w_names)}. "
                "Проанализируй этот список в динамике, сделай профессиональный разбор. "
                "Что преобладало, какие тенденции, и куда это ведет."
            )

            await bot.api.messages.send(peer_id=peer_id, message="ЧИТАЮ ЛИНИИ ВЕРОЯТНОСТИ... Анализирую состояние звезд...", random_id=0)
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")

            synthesis_result = await generate_text(synthesis_prompt, skin=active_skin)
            if synthesis_result:
                await bot.api.messages.send(peer_id=peer_id, random_id=0, message=f"✦ ЕЖЕНЕДЕЛЬНЫЙ СИНТЕЗ ✦\n\n{synthesis_result}")

            await update_user(vk_id, {
                "visit_streak": 0,
                "weekly_log": []
            })
    except Exception as e:
        logger.error(f"Global error in card_of_day_logic for vk_id={vk_id}: {str(e)}")
        try:
            await bot.api.messages.send(
                peer_id=peer_id,
                message="🔮 Произошла ошибка на стороне Оракула при вытягивании карты. Связь с потоком временно потеряна. Пожалуйста, попробуй позже.",
                random_id=0
            )
        except Exception:
            pass
    finally:
        await release_lock(vk_id)

@labeler.message(state=MyStates.WAITING_ORACLE_QUESTION)
async def process_oracle_question(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
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


