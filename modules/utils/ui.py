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
    Умное редактирование сообщения («Призрачный интерфейс 2.0»).
    Если ID не передан, пытается найти последнее сообщение бота в Redis.
    Если редактирование не удается, удаляет старое и шлет новое.
    """
    if isinstance(keyboard, dict):
        keyboard = json.dumps(keyboard, ensure_ascii=False)

    # Пытаемся получить ID из Redis, если не передано явно
    if not conversation_message_id and not message_id:
        conversation_message_id = await get_last_bot_msg(peer_id)

    # Если просят явно удалить перед отправкой
    if delete_last:
        last_id = conversation_message_id or message_id or await get_last_bot_msg(peer_id)
        if last_id:
            await delete_bot_message(bot_api, peer_id, cmid=last_id if conversation_message_id else None, mid=last_id if message_id else None)
            conversation_message_id = message_id = None

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
        logger.warning(f"Ghost edit failed, attempting recovery: {e}")
        # Если не удалось отредактировать, пробуем удалить "битое" сообщение
        if conversation_message_id:
            await delete_bot_message(bot_api, peer_id, cmid=conversation_message_id)
        elif message_id:
            await delete_bot_message(bot_api, peer_id, mid=message_id)

    # Отправка нового сообщения
    if "random_id" not in kwargs:
        kwargs["random_id"] = 0
    resp = await bot_api.messages.send(
        peer_id=peer_id,
        message=message,
        keyboard=keyboard,
        attachment=attachment,
        **kwargs
    )

    # Сохраняем ID нового сообщения (vkbottle возвращает mid)
    if isinstance(resp, int):
        await set_last_bot_msg(peer_id, resp)

    # Обновляем кэш тайпинга
    if peer_id in _typing_msg_ids:
        _typing_msg_ids[peer_id] = resp

    return resp

async def send_temp_message(bot_api, peer_id: int, message: str, delay: int = 5, **kwargs):
    """Отправляет временное сообщение, которое удаляется через delay секунд"""
    try:
        if "random_id" not in kwargs:
            kwargs["random_id"] = 0
        mid = await bot_api.messages.send(peer_id=peer_id, message=message, **kwargs)

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
    """Запускает цикл театральных фраз с обновлением последнего сообщения"""
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
                        # Ищем последнее сообщение в Redis перед отправкой нового
                        msg_id = await get_last_bot_msg(peer_id)

                    if msg_id:
                        try:
                            # Пробуем редактировать
                            await bot_api.messages.edit(peer_id=peer_id, message=phrase, conversation_message_id=msg_id)
                            await set_last_bot_msg(peer_id, msg_id)
                        except Exception:
                            # Если не вышло — шлем новое
                            msg_id = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                            await set_last_bot_msg(peer_id, msg_id)
                    else:
                        msg_id = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                        await set_last_bot_msg(peer_id, msg_id)

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
