import json
from modules.utils.consts import (
    THEATRICAL_PHRASES, _typing_tasks, _typing_msg_ids
)
from loguru import logger
import random
import asyncio

async def ghost_edit(
    bot_api,
    peer_id: int,
    message: str,
    conversation_message_id: int = None,
    message_id: int = None,
    keyboard: str = None,
    attachment: str = None,
    **kwargs
):
    try:
        if isinstance(keyboard, dict):
            keyboard = json.dumps(keyboard, ensure_ascii=False)

        if conversation_message_id:
            await bot_api.messages.edit(
                peer_id=peer_id,
                message=message,
                conversation_message_id=conversation_message_id,
                keyboard=keyboard,
                attachment=attachment,
                **kwargs
            )
            return
        elif message_id:
            await bot_api.messages.edit(
                peer_id=peer_id,
                message=message,
                message_id=message_id,
                keyboard=keyboard,
                attachment=attachment,
                **kwargs
            )
            return
    except Exception as e:
        logger.warning(f"Ghost edit failed (id={conversation_message_id or message_id}): {e}")
        # Если это ошибка 901 (no access), возможно сообщение слишком старое для редактирования
        # В таком случае мы просто отправим новое.

    # Если редактирование не удалось или не запрашивалось, отправляем новое сообщение
    return await bot_api.messages.send(
        peer_id=peer_id,
        message=message,
        keyboard=keyboard,
        attachment=attachment,
        random_id=0,
        **kwargs
    )

async def stop_dynamic_typing(peer_id: int) -> int | None:
    msg_id = _typing_msg_ids.pop(peer_id, None)
    if peer_id in _typing_tasks:
        task = _typing_tasks.pop(peer_id)
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    return msg_id

async def start_dynamic_typing(bot_api, peer_id: int, conversation_message_id: int = None) -> asyncio.Task:
    await stop_dynamic_typing(peer_id)

    async def _typing_loop():
        last_phrase = None
        msg_id = None
        if conversation_message_id:
            msg_id = conversation_message_id

        try:
            while True:
                try:
                    available_phrases = [p for p in THEATRICAL_PHRASES if p != last_phrase]
                    phrase = random.choice(available_phrases) if available_phrases else random.choice(THEATRICAL_PHRASES)
                    last_phrase = phrase

                    if msg_id is None:
                        resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                        msg_id = resp
                        _typing_msg_ids[peer_id] = msg_id
                    else:
                        try:
                            if conversation_message_id and msg_id == conversation_message_id:
                                await bot_api.messages.edit(peer_id=peer_id, message=phrase, conversation_message_id=msg_id)
                            else:
                                await bot_api.messages.edit(peer_id=peer_id, message=phrase, message_id=msg_id)
                        except Exception as edit_err:
                            # Если не удалось отредактировать (например, сообщение удалено), шлем новое
                            logger.debug(f"Typing edit failed, sending new: {edit_err}")
                            resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                            msg_id = resp
                            _typing_msg_ids[peer_id] = msg_id

                    await bot_api.messages.set_activity(peer_id=peer_id, type="typing")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug(f"Typing error: {e}")
                await asyncio.sleep(4)
        finally:
            if peer_id in _typing_tasks and _typing_tasks[peer_id] == asyncio.current_task():
                _typing_tasks.pop(peer_id, None)

    task = asyncio.create_task(_typing_loop())
    _typing_tasks[peer_id] = task
    return task
