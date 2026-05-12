import asyncio
import datetime
import json
import random
import re

from loguru import logger
from vkbottle import Callback, Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from ai_service import extract_tags, generate_section, generate_text
from cache import acquire_lock, get_tarot_names, release_lock
from cards_data import get_card_data
from database import get_user, set_user_state, update_user
from modules.bot_init import bot
from modules.states import MyStates
from modules.utils import (
    get_fsm_step,
    get_sections_keyboard,
    start_dynamic_typing,
    stop_dynamic_typing,
    upload_local_photo,
)

labeler = BotLabeler()

async def is_waiting_oracle_cut(message: Message) -> bool:
    if message.text:
        if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]):
            return False
        if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар"]:
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

        # Создаем пул из 10 случайных карт для выбора
        pool = list(range(0, 78))
        random.shuffle(pool)
        pool = pool[:10]

        await set_user_state(vk_id, json.dumps({
            "step": "oracle_draw",
            "question": question,
            "drawn_cards": [],
            "pool": pool
        }))

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

async def process_oracle_final(vk_id: int, text: str, card_ids: list, **kwargs):
    if not await acquire_lock(vk_id): return
    try:
        event_id = kwargs.get("event_id")
        conv_msg_id = kwargs.get("conversation_message_id")
        message_id = kwargs.get("message_id")

        if event_id:
            try:
                await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=vk_id, peer_id=vk_id)
            except Exception: pass

        if conv_msg_id:
            try:
                await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message="Раскладываю карты...", keyboard=Keyboard(inline=True).get_json())
            except Exception: pass
        elif message_id:
            try:
                await bot.api.messages.edit(peer_id=vk_id, message_id=message_id, message="Раскладываю карты...", keyboard=Keyboard(inline=True).get_json())
            except Exception: pass

        logger.info(f"process_oracle_final triggered for vk_id={vk_id}")
        user = await get_user(vk_id)
        if not user:
            return

        # Запускаем динамический набор текста
        await start_dynamic_typing(vk_id, bot.api)

        attachments = []
        for cid in card_ids:
            photo = await upload_local_photo(bot.api, f"{cid}.jpeg", peer_id=vk_id)
            if photo:
                attachments.append(photo)

        tarot_names = await get_tarot_names()
        c_names = [tarot_names.get(str(cid), f"Карта {cid}") for cid in card_ids]

        active_skin = user.get("active_skin", "olesya")
        purchased = user.get("purchased_sections", {})
        sex_val = purchased.get("sex_val", 0)
        gender_str = "ЖЕНЩИНА" if sex_val == 1 else "МУЖЧИНА"

        core_profile = user.get("core_profile", "")
        tags = user.get("tags", [])

        prompt = (
            f"КОНТЕКСТ: {gender_str}. "
        )
        if core_profile:
            prompt += f"Прошлый анализ: {core_profile}. "
        if tags:
            prompt += f"Фокус на прошлых темах: [{', '.join(tags)}]. "

        prompt += (
            f"Пользователь задает вопрос: {text}. "
            f"Выпали карты: 1. {c_names[0]}, 2. {c_names[1]}, 3. {c_names[2]}. "
            "Сначала выведи: Карта [N]: [Название] - [Краткий смысл]. Только потом делай общий синтез."
        )

        result_text = await generate_text(prompt, skin=active_skin)

        if not result_text:
            err_msg = "Оракул молчит. Попробуй позже."
            if conv_msg_id:
                await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message=err_msg)
            elif message_id:
                await bot.api.messages.edit(peer_id=vk_id, message_id=message_id, message=err_msg)
            else:
                await bot.api.messages.send(peer_id=vk_id, message=err_msg, random_id=0)
            return

        # Обновляем состояние Оракула и личный Гримуар
        unlocked_cards = user.get("unlocked_cards", {})
        if not isinstance(unlocked_cards, dict): unlocked_cards = {}

        for cid_int in card_ids:
            cid = str(cid_int)
            if cid not in unlocked_cards:
                grimoire_prompt = f"Краткая суть карты {tarot_names.get(cid)}. Мистично, для личного Гримуара."
                signature = await generate_text(grimoire_prompt, skin=active_skin)
                unlocked_cards[cid] = signature if signature else "Первое касание"

        await update_user(vk_id, {
            "unlocked_cards": unlocked_cards,
            "total_cards_received": user.get("total_cards_received", 0) + 3
        })

        kb_json = await get_sections_keyboard(vk_id, user)
        try:
            import json
            kb_data = json.loads(kb_json)
            if "buttons" in kb_data:
                kb_data["buttons"].insert(0, [{
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "gen_pdf", "section": "oracle", "card": str(card_ids[0]) if card_ids else ""}),
                        "label": "СГЕНЕРИРОВАТЬ PDF"
                    },
                    "color": "secondary"
                }])
            kb_json = json.dumps(kb_data, ensure_ascii=False)
        except Exception:
            pass

        if conv_msg_id:
            try:
                await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message=result_text, keyboard=kb_json, attachment=",".join(attachments))
            except Exception:
                await bot.api.messages.send(peer_id=vk_id, message=result_text, keyboard=kb_json, random_id=0, attachment=",".join(attachments))
        elif message_id:
            try:
                await bot.api.messages.edit(peer_id=vk_id, message_id=message_id, message=result_text, keyboard=kb_json, attachment=",".join(attachments))
            except Exception:
                await bot.api.messages.send(peer_id=vk_id, message=result_text, keyboard=kb_json, random_id=0, attachment=",".join(attachments))
        else:
            await bot.api.messages.send(peer_id=vk_id, message=result_text, keyboard=kb_json, random_id=0, attachment=",".join(attachments))

    except Exception as e:
        logger.error(f"Ошибка в Оракуле: {e}")
        try:
            err_msg = "Кажется, сегодня звёзды немного запутались. Попробуем ещё раз позже."
            if conv_msg_id:
                await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message=err_msg)
            elif message_id:
                await bot.api.messages.edit(peer_id=vk_id, message_id=message_id, message=err_msg)
            else:
                await bot.api.messages.send(peer_id=vk_id, message=err_msg, random_id=0)
        except Exception:
            pass
    finally:
        stop_dynamic_typing(vk_id)
        await release_lock(vk_id)

@labeler.message(text=["Карта дня", "✦ Карта дня", "🃏 Карта дня", "🃏 КАРТА ДНЯ"])
async def card_of_day_handler(message: Message):
    if not await acquire_lock(message.from_id):
        return
    try:
        msg_id = await message.answer("Открываю гримуар...", keyboard=Keyboard(inline=True).get_json())
        await card_of_day_logic(message.from_id, message.peer_id, message_id=msg_id)
    finally:
        await release_lock(message.from_id)

async def card_of_day_logic(vk_id: int, peer_id: int, **kwargs):
    try:
        event_id = kwargs.get("event_id")
        conv_msg_id = kwargs.get("conversation_message_id")
        message_id = kwargs.get("message_id")

        # 1. Сразу отвечаем ВК, если есть event_id
        if event_id:
            try:
                await bot.api.messages.send_message_event_answer(
                    event_id=event_id, user_id=vk_id, peer_id=peer_id
                )
            except Exception: pass

        # 2. Визуальный отклик
        if conv_msg_id:
            try:
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_msg_id, message="Достаю карту...", keyboard=Keyboard(inline=True).get_json())
            except Exception: pass
        elif message_id:
            try:
                await bot.api.messages.edit(peer_id=peer_id, message_id=message_id, message="Достаю карту...", keyboard=Keyboard(inline=True).get_json())
            except Exception: pass

        # 3. Получаем данные
        user = await get_user(vk_id)
        if not user:
            return

        # 4. Проверка лимита 24 часа
        purchased = user.get("purchased_sections", {})
        last_used_str = purchased.get("card_of_day_last_used")
        if last_used_str:
            last_time = datetime.datetime.fromisoformat(last_used_str)
            if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() < 24 * 3600:
                err_msg = "Твой лимит на сегодня исчерпан. Попробуй завтра или спроси Оракула."
                if conv_msg_id:
                    await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_msg_id, message=err_msg)
                elif message_id:
                    await bot.api.messages.edit(peer_id=peer_id, message_id=message_id, message=err_msg)
                else:
                    await bot.api.messages.send(peer_id=peer_id, message=err_msg, random_id=0)
                return

        await start_dynamic_typing(peer_id, bot.api)

        card_id = str(random.randint(0, 77))
        card_data = get_card_data(card_id)
        active_skin = user.get("active_skin", "olesya")
        tags = user.get("tags", [])

        # 5. Генерация разбора
        res_data = await generate_section(
            "card_of_day",
            user.get("birth_date"), user.get("birth_time"), user.get("birth_city"),
            user.get("core_profile"), user.get("first_name"), user.get("sex_val", 0),
            skin=active_skin, card_id=card_id, card_data=card_data, tags=tags, return_json=True
        )

        if not res_data:
            raise Exception("Empty result from generate_section")

        res_text_raw = res_data.get("text", "") if isinstance(res_data, dict) else res_data
        # Очищаем от тех. тегов ID_ТАРО
        result_text = re.sub(r"ID_?ТАРО:\s*\d+", "", res_text_raw).strip()

        # Фоновое сохранение тегов
        async def background_tags(text):
            new_tags = await extract_tags(text)
            if new_tags: await update_user(vk_id, {"tags": new_tags})
        asyncio.create_task(background_tags(result_text))

        # 6. Обновление баланса и статистики
        new_streak = user.get("visit_streak", 0) + 1
        unlocked = user.get("unlocked_cards", {})
        if not isinstance(unlocked, dict): unlocked = {}
        if card_id not in unlocked: unlocked[card_id] = "Первое касание"

        save_data = {
            "latest_reading_text": result_text,
            "balance": user.get("balance", 0) + 100,
            "visit_streak": new_streak,
            "unlocked_cards": unlocked,
            "total_cards_received": user.get("total_cards_received", 0) + 1,
            "purchased_sections": {**purchased, "card_of_day_last_used": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        }
        if isinstance(res_data, dict):
            res_data["text"] = result_text
            save_data["latest_reading_data"] = res_data

        await update_user(vk_id, save_data)

        # 7. Отправка результата
        photo = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=peer_id)
        final_kb = await get_sections_keyboard(vk_id, user)
        try:
            import json
            kb_data = json.loads(final_kb)
            if "buttons" in kb_data:
                kb_data["buttons"].insert(0, [{
                    "action": {
                        "type": "callback",
                        "payload": json.dumps({"cmd": "gen_pdf", "section": "card_of_day", "card": card_id}),
                        "label": "СГЕНЕРИРОВАТЬ PDF"
                    },
                    "color": "secondary"
                }])
            final_kb = json.dumps(kb_data, ensure_ascii=False)
        except Exception:
            pass

        display_text = result_text
        if isinstance(res_data, dict):
            act_lvl = res_data.get('activation_level')
            if act_lvl:
                display_text += f"\n\n⚡ УРОВЕНЬ АКТИВАЦИИ: {act_lvl}%"
                if res_data.get('activation_comment'):
                    display_text += f"\n{res_data.get('activation_comment')}"

            if res_data.get('affirmations'):
                display_text += f"\n\nТвои аффирмации:\n{res_data.get('affirmations')}"

            display_text += "\n\nПолный разбор со всеми 10 блоками доступен в PDF."

        if conv_msg_id:
            try:
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_msg_id, message=display_text, attachment=photo, keyboard=final_kb)
            except Exception:
                await bot.api.messages.send(peer_id=peer_id, message=display_text, attachment=photo, keyboard=final_kb, random_id=0)
        elif message_id:
            try:
                await bot.api.messages.edit(peer_id=peer_id, message_id=message_id, message=display_text, attachment=photo, keyboard=final_kb)
            except Exception:
                await bot.api.messages.send(peer_id=peer_id, message=display_text, attachment=photo, keyboard=final_kb, random_id=0)
        else:
            await bot.api.messages.send(peer_id=peer_id, message=display_text, attachment=photo, keyboard=final_kb, random_id=0)

    except Exception as e:
        logger.error(f"Ошибка в Карте Дня: {e}")
        try:
            err_msg = "Кажется, сегодня звёзды немного запутались. Попробуем ещё раз позже."
            if conv_msg_id:
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_msg_id, message=err_msg)
            elif message_id:
                await bot.api.messages.edit(peer_id=peer_id, message_id=message_id, message=err_msg)
            else:
                await bot.api.messages.send(peer_id=peer_id, message=err_msg, random_id=0)
        except Exception:
            pass
    finally:
        stop_dynamic_typing(peer_id)

@labeler.message(state=MyStates.WAITING_ORACLE_QUESTION)
async def process_oracle_question(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        await set_user_state(vk_id, json.dumps({"step": "oracle_cut", "question": message.text.strip()}))
        kb = Keyboard(inline=True).add(Text("✦ ОБРЕЗАТЬ КОЛОДУ"), color=KeyboardButtonColor.PRIMARY)
        await message.answer("ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже, чтобы обрезать колоду", keyboard=kb.get_json())
    finally:
        await release_lock(vk_id)
