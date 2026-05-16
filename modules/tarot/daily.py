import random
import datetime
import json
import asyncio
from loguru import logger
from modules.utils import ghost_edit
from database import get_user, update_user
from ai_service import generate_section, extract_tags, clean_ai_json
from modules.bot_init import bot
from modules.utils import (
    ghost_edit, start_dynamic_typing, stop_dynamic_typing,
    upload_local_photo, get_sections_keyboard
)
from cache import acquire_lock, release_lock

async def card_of_day_logic(vk_id: int, peer_id: int, skip_lock: bool = False, **kwargs):
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        conv_msg_id, message_id = kwargs.get("conversation_message_id"), kwargs.get("message_id")
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conv_msg_id)
        user = await get_user(vk_id)
        if not user: return

        purchased = user.get("purchased_sections", {})
        last_used_str = purchased.get("card_of_day_last_used")
        if last_used_str:
            last_time = datetime.datetime.fromisoformat(last_used_str)
            if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() < 24 * 3600:
                err_msg = "Твой лимит на сегодня исчерпан. Попробуй завтра или спроси Оракула."
                if conv_msg_id: await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_msg_id, message=err_msg)
                else: await bot.api.messages.send(peer_id=peer_id, message=err_msg, random_id=0)
                return

        # Интерактивное перемешивание
        shuffle_steps = [
            "🃏 Тасовка колоды...",
            "🌀 Настройка частоты...",
            "✨ Извлечение карты..."
        ]
        curr_msg_id = None
        for step in shuffle_steps:
            text = f"✦ КАРТА ДНЯ ✦\n\n{step}"
            if conv_msg_id:
                await bot.api.messages.edit(peer_id=peer_id, message=text, conversation_message_id=conv_msg_id)
            elif curr_msg_id:
                await bot.api.messages.edit(peer_id=peer_id, message=text, message_id=curr_msg_id)
            else:
                curr_msg_id = await bot.api.messages.send(peer_id=peer_id, message=text, random_id=0)
                from modules.utils.consts import _typing_msg_ids
                _typing_msg_ids[peer_id] = curr_msg_id
            await asyncio.sleep(1)

        card_id = str(random.randint(0, 77))
        res_data = await generate_section(
            section="card_of_day", date=user.get("birth_date", ""), time=user.get("birth_time", "12:00"),
            city=user.get("birth_city", ""), core_profile=user.get("core_profile", ""),
            first_name=user.get("first_name", ""), sex=user.get("sex_val", 0),
            skin=user.get("active_skin", "olesya"), tags=user.get("tags", []), return_json=True
        )
        if not res_data: raise Exception("Empty result")

        if isinstance(res_data, dict): parsed, result_text = res_data, res_data.get("text", "")
        else:
            clean_text = clean_ai_json(res_data)
            try:
                parsed = json.loads(clean_text) if clean_text.startswith("{") else {}
                result_text = parsed.get("text", clean_text)
            except:
                parsed, result_text = {}, clean_text

        async def background_tags(text):
            new_tags = await extract_tags(text)
            if new_tags: await update_user(vk_id, {"tags": new_tags})
        asyncio.create_task(background_tags(result_text))

        await update_user(vk_id, {
            "latest_reading_text": result_text, "latest_reading_data": parsed if parsed else {"text": result_text},
            "balance": user.get("balance", 0) + 100, "visit_streak": user.get("visit_streak", 0) + 1,
            "unlocked_cards": {**user.get("unlocked_cards", {}), card_id: "Первое касание"},
            "total_cards_received": user.get("total_cards_received", 0) + 1,
            "purchased_sections": {**purchased, "card_of_day_last_used": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        })

        photo = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=peer_id)
        final_kb = await get_sections_keyboard(vk_id, user)
        try:
            kb_data = json.loads(final_kb)
            if "buttons" in kb_data:
                kb_data["buttons"].insert(0, [{"action": {"type": "callback", "payload": json.dumps({"cmd": "gen_pdf", "section": "card_of_day", "card": card_id}), "label": "СГЕНЕРИРОВАТЬ PDF"}, "color": "secondary"}])
            final_kb = json.dumps(kb_data, ensure_ascii=False)
        except: pass

        typing_msg_id = await stop_dynamic_typing(peer_id)
        await ghost_edit(bot.api, peer_id, message=result_text + "\n\nПолный разбор со всеми 10 блоками доступен в PDF.", conversation_message_id=conv_msg_id, message_id=message_id or typing_msg_id, attachment=photo, keyboard=final_kb)
    except Exception as e:
        logger.error(f"Ошибка в Карте Дня: {e}")
        err_msg = "Кажется, сегодня звёзды немного запутались. Попробуем ещё раз позже."
        if conv_msg_id: await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_msg_id, message=err_msg)
        else: await bot.api.messages.send(peer_id=peer_id, message=err_msg, random_id=0)
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock: await release_lock(vk_id)
