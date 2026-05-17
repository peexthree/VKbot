import datetime
import json
import asyncio
from loguru import logger
from vkbottle import Keyboard, Callback, KeyboardButtonColor
from database import get_user, set_user_state
from modules.bot_init import bot
from modules.utils import (
    ghost_edit, start_dynamic_typing, stop_dynamic_typing,
    upload_local_photo, get_last_bot_msg, delete_bot_message
)
from cache import acquire_lock, release_lock

async def card_of_day_logic(vk_id: int, peer_id: int, skip_lock: bool = False, **kwargs):
    if not skip_lock and not await acquire_lock(vk_id): return
    try:
        conv_msg_id = kwargs.get("conversation_message_id")
        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conv_msg_id)
        user = await get_user(vk_id)
        if not user: return

        purchased = user.get("purchased_sections", {})
        last_used_str = purchased.get("card_of_day_last_used")
        if last_used_str:
            last_time = datetime.datetime.fromisoformat(last_used_str)
            if (datetime.datetime.now(datetime.timezone.utc) - last_time).total_seconds() < 24 * 3600:
                err_msg = "Ты уже получил напутствие на сегодня. Возвращайся завтра или спроси совета у Оракула ✨"
                await stop_dynamic_typing(peer_id)
                await ghost_edit(bot.api, peer_id, message=err_msg, conversation_message_id=conv_msg_id)
                return

        await set_user_state(vk_id, json.dumps({"step": "global_cut", "target_section": "card_of_day"}))
        kb = Keyboard(inline=True).add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
        att = await upload_local_photo(bot.api, "uslugi/cardofday.jpg", peer_id=peer_id)

        # РИТУАЛ (2 секунды для плавности)
        await asyncio.sleep(2)

        typing_msg_id = await stop_dynamic_typing(peer_id)

        await ghost_edit(
            bot_api=bot.api,
            peer_id=peer_id,
            message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ.\n\nКолода готова почувствовать твою энергию. Жми кнопку ниже.",
            conversation_message_id=conv_msg_id,
            message_id=typing_msg_id,
            attachment=att,
            keyboard=kb.get_json()
        )
    except Exception as e:
        logger.error(f"Ошибка в Карте Дня: {e}")
        err_msg = "Кажется, Вселенная сейчас хранит молчание. Попробуй заглянуть чуть позже ✨"
        await stop_dynamic_typing(peer_id)
        await ghost_edit(bot.api, peer_id, message=err_msg, conversation_message_id=conv_msg_id)
    finally:
        await stop_dynamic_typing(peer_id)
        if not skip_lock: await release_lock(vk_id)
