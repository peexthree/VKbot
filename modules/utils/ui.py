import json
from modules.utils.consts import (
    THEATRICAL_PHRASES, _typing_tasks, _typing_msg_ids
)
from loguru import logger
import random
import asyncio
from cache import redis_client

async def delete_bot_message(bot_api, peer_id: int, cmid: int = None, mid: int = None):
    """Безопасное удаление сообщения бота"""
    try:
        if cmid:
            await bot_api.messages.delete(peer_id=peer_id, conversation_message_ids=[cmid], delete_for_all=True)
        elif mid:
            await bot_api.messages.delete(peer_id=peer_id, message_ids=[mid], delete_for_all=True)
    except Exception as e:
        logger.debug(f"Failed to delete message: {e}")

async def get_last_bot_msg(peer_id: int) -> int | None:
    """Получает CMID последнего сообщения бота из кэша"""
    res = await redis_client.get(f"last_bot_msg:{peer_id}")
    return int(res) if res else None

async def set_last_bot_msg(peer_id: int, cmid: int):
    """Запоминает CMID последнего сообщения бота"""
    await redis_client.set(f"last_bot_msg:{peer_id}", str(cmid), ex=86400)

async def ghost_edit(
    bot_api,
    peer_id: int,
    message: str,
    conversation_message_id: int = None,
    message_id: int = None,
    keyboard: str = None,
    attachment: str = None,
    delete_last: bool = False,
    **kwargs
):
    """
    Ghost Interface 2.0: Редактирует существующее сообщение или удаляет старое и шлет новое.
    Всегда стремится оставить только ОДНО активное сообщение в чате.
    """
    if isinstance(keyboard, dict):
        keyboard = json.dumps(keyboard, ensure_ascii=False)

    # Пытаемся найти последнее сообщение, если ID не передан
    if not conversation_message_id and not message_id:
        last_id = await get_last_bot_msg(peer_id)
        if last_id:
            # В VK для личных сообщений CMID часто совпадает с MID
            conversation_message_id = last_id

    # Если включен режим delete_last или мы не можем редактировать
    if delete_last:
        last_id = await get_last_bot_msg(peer_id)
        if last_id:
            await delete_bot_message(bot_api, peer_id, cmid=last_id)
            conversation_message_id = None
            message_id = None

    try:
        if conversation_message_id:
            await bot_api.messages.edit(
                peer_id=peer_id,
                message=message,
                conversation_message_id=conversation_message_id,
                keyboard=keyboard,
                attachment=attachment,
                **kwargs
            )
            await set_last_bot_msg(peer_id, conversation_message_id)
            return conversation_message_id
        elif message_id:
            await bot_api.messages.edit(
                peer_id=peer_id,
                message=message,
                message_id=message_id,
                keyboard=keyboard,
                attachment=attachment,
                **kwargs
            )
            await set_last_bot_msg(peer_id, message_id)
            return message_id
    except Exception as e:
        logger.debug(f"Ghost edit failed (ID={conversation_message_id or message_id}), sending new: {e}")
        # Если не удалось отредактировать, удаляем то, что пытались (если оно еще есть)
        if conversation_message_id:
            await delete_bot_message(bot_api, peer_id, cmid=conversation_message_id)
        elif message_id:
            await delete_bot_message(bot_api, peer_id, mid=message_id)

    # Отправка нового сообщения
    try:
        resp = await bot_api.messages.send(
            peer_id=peer_id,
            message=message,
            keyboard=keyboard,
            attachment=attachment,
            random_id=0,
            **kwargs
        )
        # Сохраняем как последнее
        if isinstance(resp, int):
            await set_last_bot_msg(peer_id, resp)
            # Обновляем глобальный кэш тайпинга
            if peer_id in _typing_msg_ids:
                _typing_msg_ids[peer_id] = resp
        return resp
    except Exception as send_err:
        logger.error(f"Critical failure in ghost_edit: {send_err}")
        return None

async def send_temp_message(bot_api, peer_id: int, message: str, delay: int = 5, **kwargs):
    """Отправляет временное сообщение, которое удаляется через delay секунд"""
    try:
        mid = await bot_api.messages.send(peer_id=peer_id, message=message, random_id=0, **kwargs)

        async def _delete_after():
            await asyncio.sleep(delay)
            await delete_bot_message(bot_api, peer_id, mid=mid)

        asyncio.create_task(_delete_after())
        return mid
    except Exception as e:
        logger.error(f"Failed to send temp message: {e}")
        return None

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
        msg_id = conversation_message_id

        try:
            while True:
                try:
                    available_phrases = [p for p in THEATRICAL_PHRASES if p != last_phrase]
                    phrase = random.choice(available_phrases) if available_phrases else random.choice(THEATRICAL_PHRASES)
                    last_phrase = phrase

                    if msg_id is None:
                        # Если не передали ID, сначала ищем в Redis
                        msg_id = await get_last_bot_msg(peer_id)

                        if msg_id is None:
                            # Если и в Redis нет, создаем новое
                            resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                            msg_id = resp
                            _typing_msg_ids[peer_id] = msg_id
                            await set_last_bot_msg(peer_id, msg_id)
                        else:
                            # Если нашли в Redis, пробуем редактировать его
                            try:
                                await bot_api.messages.edit(peer_id=peer_id, message=phrase, conversation_message_id=msg_id)
                                _typing_msg_ids[peer_id] = msg_id
                            except:
                                # Если не удалось (например, сообщение слишком старое или удалено)
                                await delete_bot_message(bot_api, peer_id, cmid=msg_id)
                                resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                                msg_id = resp
                                _typing_msg_ids[peer_id] = msg_id
                                await set_last_bot_msg(peer_id, msg_id)
                    else:
                        try:
                            # Если мы редактируем существующее сообщение по CMID
                            await bot_api.messages.edit(peer_id=peer_id, message=phrase, conversation_message_id=msg_id)
                            await set_last_bot_msg(peer_id, msg_id)
                        except Exception as edit_err:
                            logger.debug(f"Typing edit failed, sending new: {edit_err}")
                            await delete_bot_message(bot_api, peer_id, cmid=msg_id)
                            resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                            msg_id = resp
                            _typing_msg_ids[peer_id] = msg_id
                            await set_last_bot_msg(peer_id, msg_id)

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
