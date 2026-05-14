import asyncio
import datetime
import json
import random
from loguru import logger
from vkbottle import Callback, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message

from ai_service import clean_ai_json, extract_tags, generate_section, generate_text
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


# ==================== ОРАКУЛ ====================
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
    if not await acquire_lock(vk_id):
        return
    try:
        conv_msg_id = kwargs.get("conversation_message_id")
        message_id = kwargs.get("message_id")

        if conv_msg_id:
            try:
                await bot.api.messages.edit(
                    peer_id=vk_id,
                    conversation_message_id=conv_msg_id,
                    message="Раскладываю карты...",
                    keyboard=Keyboard(inline=True).get_json()
                )
            except Exception:
                pass
        elif message_id:
            try:
                await bot.api.messages.edit(
                    peer_id=vk_id,
                    message_id=message_id,
                    message="Раскладываю карты...",
                    keyboard=Keyboard(inline=True).get_json()
                )
            except Exception:
                pass

        user = await get_user(vk_id)
        if not user:
            return

        await start_dynamic_typing(bot.api, vk_id)

        # Загружаем фото карт
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

        prompt = f"КОНТЕКСТ: {gender_str}. "
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
            else:
                await bot.api.messages.send(peer_id=vk_id, message=err_msg, random_id=0)
            return

        # Обновляем Гримуар
        unlocked_cards = user.get("unlocked_cards", {}) or {}
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

        # Клавиатура
        kb_json = await get_sections_keyboard(vk_id, user)
        try:
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
                await bot.api.messages.edit(
                    peer_id=vk_id,
                    conversation_message_id=conv_msg_id,
                    message=result_text,
                    keyboard=kb_json,
                    attachment=",".join(attachments) if attachments else None
                )
            except Exception:
                await bot.api.messages.send(peer_id=vk_id, message=result_text, keyboard=kb_json, random_id=0, attachment=",".join(attachments) if attachments else None)
        else:
            await bot.api.messages.send(peer_id=vk_id, message=result_text, keyboard=kb_json, random_id=0, attachment=",".join(attachments) if attachments else None)

    except Exception as e:
        logger.error(f"Ошибка в Оракуле: {e}")
        err_msg = "Кажется, сегодня звёзды немного запутались. Попробуем ещё раз позже."
        if conv_msg_id:
            await bot.api.messages.edit(peer_id=vk_id, conversation_message_id=conv_msg_id, message=err_msg)
        else:
            await bot.api.messages.send(peer_id=vk_id, message=err_msg, random_id=0)
    finally:
        await stop_dynamic_typing(vk_id)
        await release_lock(vk_id)


# ==================== КАРТА ДНЯ ====================
@labeler.message(text=["Карта дня", "✦ Карта дня", "🃏 Карта дня", "🃏 КАРТА ДНЯ"])
async def card_of_day_handler(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        await card_of_day_logic(vk_id, message.peer_id, conversation_message_id=message.conversation_message_id)
    finally:
        await release_lock(vk_id)


async def card_of_day_logic(vk_id: int, peer_id: int, skip_lock: bool = False, **kwargs):
    """Исправленная и стабильная Карта Дня"""
    if not skip_lock and not await acquire_lock(vk_id):
        return
    try:
        event_id = kwargs.get("event_id")
        conv_msg_id = kwargs.get("conversation_message_id")
        message_id = kwargs.get("message_id")

        # Используем наш новый механизм динамического тайпинга
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conv_msg_id)

        user = await get_user(vk_id)
        if not user:
            return

        # Лимит 24 часа
        purchased = user.get("purchased_sections", {})
        last_used_str = purchased.get("card_of_day_last_used")
        if last_used_str:
            last_time = datetime.datetime.fromisoformat(last_used_str)
            if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() < 24 * 3600:
                err_msg = "Твой лимит на сегодня исчерпан. Попробуй завтра или спроси Оракула."
                if conv_msg_id:
                    await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_msg_id, message=err_msg)
                else:
                    await bot.api.messages.send(peer_id=peer_id, message=err_msg, random_id=0)
                return

        card_id = str(random.randint(0, 77))
        card_data = get_card_data(card_id)
        active_skin = user.get("active_skin", "olesya")
        tags = user.get("tags", [])

        res_data = await generate_section(
            section="card_of_day",
            date=user.get("birth_date", ""),
            time=user.get("birth_time", "12:00"),
            city=user.get("birth_city", ""),
            core_profile=user.get("core_profile", ""),
            first_name=user.get("first_name", ""),
            sex=user.get("sex_val", 0),
            skin=active_skin,
            tags=tags,
            return_json=True
        )

        if not res_data:
            raise Exception("Empty result from generate_section")

        # === ИСПРАВЛЕННЫЙ ПАРСИНГ JSON ===
        if isinstance(res_data, dict):
            parsed = res_data
            result_text = parsed.get("text", "")
        else:
            clean_text = clean_ai_json(res_data)
            try:
                parsed = json.loads(clean_text) if clean_text.startswith("{") else {}
            except json.JSONDecodeError:
                parsed = {}
                result_text = clean_text
            else:
                result_text = parsed.get("text", clean_text)

        # Фоновое сохранение тегов
        async def background_tags(text):
            new_tags = await extract_tags(text)
            if new_tags:
                await update_user(vk_id, {"tags": new_tags})
        asyncio.create_task(background_tags(result_text))

        # Обновление БД (правильная колонка!)
        save_data = {
            "latest_reading_text": result_text,
            "latest_reading_data": parsed if parsed else {"text": result_text},
            "balance": user.get("balance", 0) + 100,
            "visit_streak": user.get("visit_streak", 0) + 1,
            "unlocked_cards": {**user.get("unlocked_cards", {}), card_id: "Первое касание"},
            "total_cards_received": user.get("total_cards_received", 0) + 1,
            "purchased_sections": {**purchased, "card_of_day_last_used": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        }
        await update_user(vk_id, save_data)

        # Отправка
        photo = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=peer_id)

        final_kb = await get_sections_keyboard(vk_id, user)
        # Исправленная клавиатура (не больше 2 кнопок в ряду!)
        try:
            kb_data = json.loads(final_kb)
            if "buttons" in kb_data:
                kb_data["buttons"].insert(0, [{
                    "action": {"type": "callback", "payload": json.dumps({"cmd": "gen_pdf", "section": "card_of_day", "card": card_id}), "label": "СГЕНЕРИРОВАТЬ PDF"},
                    "color": "secondary"
                }])
            final_kb = json.dumps(kb_data, ensure_ascii=False)
        except Exception:
            pass

        display_text = result_text + "\n\nПолный разбор со всеми 10 блоками доступен в PDF."

        typing_msg_id = await stop_dynamic_typing(peer_id)
        from modules.utils import ghost_edit
        await ghost_edit(
            bot.api,
            peer_id,
            message=display_text,
            conversation_message_id=conv_msg_id,
            message_id=message_id or typing_msg_id,
            attachment=photo,
            keyboard=final_kb
        )

    except Exception as e:
        logger.error(f"Ошибка в Карте Дня: {e}")
        err_msg = "Кажется, сегодня звёзды немного запутались. Попробуем ещё раз позже."
        if conv_msg_id:
            await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_msg_id, message=err_msg)
        elif message_id:
            await bot.api.messages.edit(peer_id=peer_id, message_id=message_id, message=err_msg)
        else:
            await bot.api.messages.send(peer_id=peer_id, message=err_msg, random_id=0)
    finally:
        await stop_dynamic_typing(peer_id)
        await release_lock(vk_id)


@labeler.message(state=MyStates.WAITING_ORACLE_QUESTION)
async def process_oracle_question(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return
    try:
        await set_user_state(vk_id, json.dumps({"step": "oracle_cut", "question": message.text.strip()}))
        kb = Keyboard(inline=True).add(Callback("✦ ОБРЕЗАТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.PRIMARY)
        await message.answer("ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже, чтобы обрезать колоду", keyboard=kb.get_json())
    finally:
        await release_lock(vk_id)
