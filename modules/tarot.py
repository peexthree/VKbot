from modules.bot_init import bot
from cache import acquire_lock, release_lock, get_tarot_names
from modules.states import MyStates
import asyncio
import json
import random
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import (
    Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
)
from database import get_user, update_user, set_user_state, get_user_state
from ai_service import generate_text, generate_section, extract_tags
from modules.utils import (
    get_fsm_step,
    upload_local_photo,
    SKIN_ASSETS,
    get_dynamic_keyboard,
    get_sections_keyboard,
    start_dynamic_typing,
    stop_dynamic_typing,
)

from loguru import logger

labeler = BotLabeler()


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

        # Создаём пул из 10 случайных карт
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
            "ШАГ 3 ИЗ 3: ВЫБОР КАРТ\n\nВыбери из своей стопки ровно 3 карты",
            keyboard=kb.get_json()
        )
    finally:
        await release_lock(vk_id)


async def process_oracle_final(vk_id: int, text: str, card_ids: list):
    """Финальная обработка расклада Оракула"""
    logger.info(f"process_oracle_final triggered for vk_id={vk_id}")
    user = await get_user(vk_id)
    if not user:
        return

    await start_dynamic_typing(vk_id, bot.api)

    try:
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

        prompt = (
            f"КОНТЕКСТ: {gender_str}. "
            f"Пользователь задаёт вопрос: {text}. "
            f"Выпали карты: 1. {c_names[0]}, 2. {c_names[1]}, 3. {c_names[2]}.\n\n"
            "Сначала выведи по каждой карте: 'Карта [N]: [Название] — [Краткий смысл]'. "
            "Только после этого делай общий синтез."
        )

        result_text = await generate_text(prompt, skin=active_skin)

        if not result_text:
            await bot.api.messages.send(
                peer_id=vk_id,
                message="Оракул сейчас молчит... Попробуй чуть позже.",
                random_id=0
            )
            return

        # Обновление Гримуара
        unlocked_cards = user.get("unlocked_cards", {}) or {}
        for cid_int in card_ids:
            cid = str(cid_int)
            if cid not in unlocked_cards:
                grimoire_prompt = f"Краткая мистическая суть карты {tarot_names.get(cid, '')} для личного Гримуара."
                signature = await generate_text(grimoire_prompt, skin=active_skin)
                unlocked_cards[cid] = signature or "Первое касание с картой"

        await update_user(vk_id, {
            "unlocked_cards": unlocked_cards,
            "total_cards_received": user.get("total_cards_received", 0) + 3
        })

        kb_json = await get_sections_keyboard(vk_id, user)

        await bot.api.messages.send(
            peer_id=vk_id,
            message=result_text,
            keyboard=kb_json,
            random_id=0,
            attachment=",".join(attachments) if attachments else None
        )

    except Exception as e:
        logger.error(f"Ошибка в process_oracle_final: {e}")
    finally:
        stop_dynamic_typing(vk_id)


@labeler.message(text=["Карта дня", "✦ Карта дня", "🃏 Карта дня", "🃏 КАРТА ДНЯ"])
async def card_of_day_handler(message: Message):
    await card_of_day_logic(message.from_id, message.peer_id)


async def card_of_day_logic(vk_id: int, peer_id: int):
    if not await acquire_lock(vk_id):
        return

    user = await get_user(vk_id)
    if not user:
        await release_lock(vk_id)
        return

    try:
        # Проверка лимита 24 часа
        purchased = user.get("purchased_sections", {})
        last_used_str = purchased.get("card_of_day_last_used")

        if last_used_str:
            last_time = datetime.datetime.fromisoformat(last_used_str)
            if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() < 24 * 3600:
                await bot.api.messages.send(
                    peer_id=peer_id,
                    message="Твой лимит на Карту Дня уже исчерпан сегодня.\n\nПопробуй завтра или обратись к Оракулу.",
                    random_id=0
                )
                return

        await start_dynamic_typing(peer_id, bot.api)

        card_id = str(random.randint(0, 77))
        active_skin = user.get("active_skin", "olesya")
        tags = user.get("tags", [])

        result_text = await generate_section(
            section="card_of_day",
            birth_date=user.get("birth_date"),
            birth_time=user.get("birth_time"),
            birth_city=user.get("birth_city"),
            core_profile=user.get("core_profile"),
            first_name=user.get("first_name"),
            sex_val=user.get("sex_val", 0),
            skin=active_skin,
            card_id=card_id,
            tags=tags
        )

        # Фоновое извлечение тегов
        async def background_tags(text: str):
            new_tags = await extract_tags(text)
            if new_tags:
                await update_user(vk_id, {"tags": new_tags})

        asyncio.create_task(background_tags(result_text))

        # Обновление статистики
        unlocked = user.get("unlocked_cards", {}) or {}
        if card_id not in unlocked:
            unlocked[card_id] = "Первое касание"

        await update_user(vk_id, {
            "balance": user.get("balance", 0) + 100,
            "visit_streak": user.get("visit_streak", 0) + 1,
            "unlocked_cards": unlocked,
            "total_cards_received": user.get("total_cards_received", 0) + 1,
            "purchased_sections": {
                **purchased,
                "card_of_day_last_used": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        })

        photo = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)

        # Специальное сообщение для первой карты
        if user.get("total_cards_received", 0) == 0:
            result_text += "\n\n✨ Это твоя первая карта в Гримуаре. Я уже сохранила её. Теперь она будет копить силу вместе с тобой."

        final_kb = await get_sections_keyboard(vk_id, user)

        await bot.api.messages.send(
            peer_id=peer_id,
            message=result_text,
            attachment=photo,
            keyboard=final_kb,
            random_id=0
        )

    except Exception as e:
        logger.error(f"Ошибка в card_of_day_logic: {e}")
    finally:
        stop_dynamic_typing(peer_id)
        await release_lock(vk_id)


@labeler.message(state=MyStates.WAITING_ORACLE_QUESTION)
async def process_oracle_question(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id):
        return

    try:
        await set_user_state(vk_id, json.dumps({
            "step": "oracle_cut",
            "question": message.text.strip()
        }))

        kb = Keyboard(inline=True).add(
            Text("✦ ОБРЕЗАТЬ КОЛОДУ"),
            color=KeyboardButtonColor.PRIMARY
        )

        await message.answer(
            "ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ\n\nНажми кнопку ниже, чтобы обрезать колоду",
            keyboard=kb.get_json()
        )
    finally:
        await release_lock(vk_id)