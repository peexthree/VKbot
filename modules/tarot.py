from __future__ import annotations
import asyncio
import datetime
import json
import random
from loguru import logger
from vkbottle import Callback, Keyboard
from vkbottle.bot import BotLabeler, Message

from ai_service import extract_tags, generate_section, generate_text
from cache import acquire_lock, get_tarot_names, release_lock
from database import get_user, set_user_state, update_user
from modules.bot_init import bot
from modules.utils import (
    get_fsm_step,
    get_sections_keyboard,
    start_dynamic_typing,
    stop_dynamic_typing,
    upload_local_photo,
)

labeler = BotLabeler()


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
async def send_or_edit(peer_id: int, text: str, keyboard=None, attachment=None, conv_msg_id=None, message_id=None):
    try:
        if conv_msg_id:
            await bot.api.messages.edit(
                peer_id=peer_id,
                conversation_message_id=conv_msg_id,
                message=text,
                keyboard=keyboard,
                attachment=attachment
            )
        elif message_id:
            await bot.api.messages.edit(
                peer_id=peer_id,
                message_id=message_id,
                message=text,
                keyboard=keyboard,
                attachment=attachment
            )
        else:
            await bot.api.messages.send(
                peer_id=peer_id,
                message=text,
                keyboard=keyboard,
                attachment=attachment,
                random_id=0
            )
    except Exception:
        # fallback
        await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=keyboard, attachment=attachment, random_id=0)


# ====================== ОРАКУЛ ======================
async def is_waiting_oracle_cut(message: Message) -> bool:
    if message.text and message.text.lower() in ["начать", "start", "/start"]:
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

        pool = list(range(78))
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
            kb.add(Callback("🎴", payload={"cmd": "oracle_card", "id": card_id}))

        await message.answer(
            "ШАГ 3 ИЗ 3: ВЫБОР КАРТ. Выбери из своей стопки ровно 3 карты",
            keyboard=kb.get_json()
        )
    finally:
        await release_lock(vk_id)


@labeler.message(func=lambda m: m.payload and m.payload.get("cmd") == "oracle_card")
async def process_oracle_card(event):
    vk_id = event.user_id
    peer_id = event.peer_id
    card_id = event.payload.get("id")

    if not await acquire_lock(vk_id):
        return
    try:
        state = await get_fsm_step(vk_id)
        if not state or state.get("step") != "oracle_draw":
            return

        drawn = state.get("drawn_cards", [])
        pool = state.get("pool", [])
        question = state.get("question", "")

        drawn.append(card_id)

        if len(drawn) < 3:
            await set_user_state(vk_id, json.dumps({
                "step": "oracle_draw",
                "question": question,
                "drawn_cards": drawn,
                "pool": pool
            }))
            await bot.api.messages.send_message_event_answer(
                event_id=event.get_id(), user_id=vk_id, peer_id=peer_id
            )
            return

        # Все 3 карты выбраны
        await set_user_state(vk_id, "")
        await process_oracle_final(
            vk_id=vk_id,
            text=question,
            card_ids=drawn,
            event_id=event.get_id(),
            peer_id=peer_id
        )
    finally:
        await release_lock(vk_id)


async def process_oracle_final(vk_id: int, text: str, card_ids: list, **kwargs):
    peer_id = kwargs.get("peer_id", vk_id)
    if not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id)

        user = await get_user(vk_id)
        if not user:
            return

        # Загрузка фото карт
        attachments = []
        for cid in card_ids:
            photo = await upload_local_photo(bot.api, f"{cid}.jpeg", peer_id=peer_id)
            if photo:
                attachments.append(photo)

        tarot_names = await get_tarot_names()
        c_names = [tarot_names.get(str(cid), f"Карта {cid}") for cid in card_ids]

        active_skin = user.get("active_skin", "olesya")
        prompt = (
            f"КОНТЕКСТ: {user.get('sex_val', 0) == 1 and 'ЖЕНЩИНА' or 'МУЖЧИНА'}. "
            f"Вопрос пользователя: {text}. "
            f"Выпали карты: 1. {c_names[0]}, 2. {c_names[1]}, 3. {c_names[2]}. "
            "Сначала выведи: Карта [N]: [Название] - [Краткий смысл]. Только потом общий синтез."
        )

        result_text = await generate_text(prompt, skin=active_skin)

        # Сохранение в гримуар
        unlocked = user.get("unlocked_cards", {}) or {}
        for cid in card_ids:
            cid_str = str(cid)
            if cid_str not in unlocked:
                signature = await generate_text(f"Краткая суть карты {tarot_names.get(cid_str)}", skin=active_skin)
                unlocked[cid_str] = signature or "Первое касание"

        await update_user(vk_id, {
            "unlocked_cards": unlocked,
            "total_cards_received": user.get("total_cards_received", 0) + 3
        })

        kb_json = await get_sections_keyboard(vk_id, user)

        await send_or_edit(
            peer_id=peer_id,
            text=result_text or "Оракул молчит сегодня...",
            keyboard=kb_json,
            attachment=",".join(attachments) if attachments else None,
            conv_msg_id=kwargs.get("conversation_message_id"),
            message_id=kwargs.get("message_id")
        )
    except Exception as e:
        logger.error(f"Ошибка в Оракуле: {e}")
        await send_or_edit(
            peer_id=peer_id,
            text="Кажется, сегодня звёзды немного запутались. Попробуем ещё раз позже.",
            conv_msg_id=kwargs.get("conversation_message_id"),
            message_id=kwargs.get("message_id")
        )
    finally:
        stop_dynamic_typing(peer_id)
        await release_lock(vk_id)


# ====================== КАРТА ДНЯ ======================
@labeler.message(text=["Карта дня", "✦ Карта дня", "🃏 Карта дня", "🃏 КАРТА ДНЯ"])
async def card_of_day_handler(message: Message):
    msg_id = await message.answer("Открываю гримуар...", keyboard=Keyboard(inline=True).get_json())
    await card_of_day_logic(message.from_id, message.peer_id, message_id=msg_id)


async def card_of_day_logic(vk_id: int, peer_id: int, **kwargs):
    if not await acquire_lock(vk_id):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id)

        user = await get_user(vk_id)
        if not user:
            return

        # Проверка лимита 24 часа
        purchased = user.get("purchased_sections", {})
        last_used = purchased.get("card_of_day_last_used")
        if last_used:
            last_time = datetime.datetime.fromisoformat(last_used)
            if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() < 24 * 3600:
                await send_or_edit(peer_id, "Твой лимит на сегодня исчерпан. Попробуй завтра.", **kwargs)
                return

        card_id = str(random.randint(0, 77))
        active_skin = user.get("active_skin", "olesya")
        tags = user.get("tags", [])

        result_text = await generate_section(
            "card_of_day",
            user.get("birth_date"),
            user.get("birth_time"),
            user.get("birth_city"),
            core_profile=user.get("core_profile", ""),
            first_name=user.get("first_name", ""),
            sex=user.get("sex_val", 0),
            skin=active_skin,
            card_id=card_id,
            tags=tags
        )

        # Фоновое сохранение тегов
        asyncio.create_task(background_save_tags(vk_id, result_text))

        # Обновление статистики
        new_streak = user.get("visit_streak", 0) + 1
        unlocked = user.get("unlocked_cards", {}) or {}
        if card_id not in unlocked:
            unlocked[card_id] = "Первое касание"

        await update_user(vk_id, {
            "balance": user.get("balance", 0) + 100,
            "visit_streak": new_streak,
            "unlocked_cards": unlocked,
            "total_cards_received": user.get("total_cards_received", 0) + 1,
            "purchased_sections": {**purchased, "card_of_day_last_used": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        })

        photo = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=peer_id)
        kb_json = await get_sections_keyboard(vk_id, user)

        await send_or_edit(
            peer_id=peer_id,
            text=result_text or "Карта дня не смогла раскрыться...",
            keyboard=kb_json,
            attachment=photo,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Ошибка в Карте Дня: {e}")
        await send_or_edit(peer_id, "Кажется, сегодня звёзды немного запутались. Попробуем ещё раз позже.", **kwargs)
    finally:
        stop_dynamic_typing(peer_id)
        await release_lock(vk_id)


async def background_save_tags(vk_id: int, text: str):
    try:
        new_tags = await extract_tags(text)
        if new_tags:
            await update_user(vk_id, {"tags": new_tags})
    except Exception as e:
        logger.error(f"Background tags error: {e}")


# ====================== ЗАВЕРШЕНИЕ ФАЙЛА ======================
logger.info("Модуль tarot.py загружен успешно")
