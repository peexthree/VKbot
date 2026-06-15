import json
from modules.utils.consts import (
    THEATRICAL_PHRASES, _typing_tasks, _typing_msg_ids
)
from loguru import logger
from vkbottle import VKAPIError
import random
import asyncio
from cache import redis_client

def extract_msg_id(resp) -> int | None:
    """Извлекает целочисленный ID сообщения из различных форматов ответа VK API"""
    if resp is None:
        return None
    if isinstance(resp, int):
        return resp
    if isinstance(resp, list) and resp:
        # Для peer_ids может вернуться список объектов
        first = resp[0]
        if isinstance(first, dict):
            return first.get("conversation_message_id") or first.get("message_id") or first.get("id")
        return extract_msg_id(first)
    if isinstance(resp, dict):
        # Если ответ обернут в 'response'
        if "response" in resp:
            return extract_msg_id(resp["response"])
        return resp.get("conversation_message_id") or resp.get("message_id") or resp.get("id")
    if isinstance(resp, str):
        # Попытка парсинга строки типа "conversation_message_id=8430 ..."
        if "conversation_message_id=" in resp:
            try:
                return int(resp.split("conversation_message_id=")[1].split()[0])
            except: pass
        if "message_id=" in resp:
            try:
                return int(resp.split("message_id=")[1].split()[0])
            except: pass
        try:
            return int(resp)
        except: pass
    return None

async def delete_bot_message(bot_api, peer_id: int, cmid: int = None, mid: int = None):
    """Безопасное удаление сообщения бота"""
    try:
        # Санитизация ID
        cmid = extract_msg_id(cmid)
        mid = extract_msg_id(mid)

        if cmid:
            await bot_api.messages.delete(peer_id=peer_id, conversation_message_ids=[cmid], delete_for_all=True)
        elif mid:
            await bot_api.messages.delete(peer_id=peer_id, message_ids=[mid], delete_for_all=True)
    except VKAPIError[15]:
        # Игнорируем ошибку, если сообщение слишком старое
        return
    except VKAPIError[3]:
        # Игнорируем, если сообщение не найдено
        return
    except Exception as e:
        # Для прочих ошибок доступа или если сообщение удалено
        if "Access denied" in str(e):
            return
        logger.debug(f"Failed to delete message: {e}")

async def get_last_bot_msg(peer_id: int) -> int | None:
    """Получает CMID последнего сообщения бота из кэша"""
    res = await redis_client.get(f"last_bot_msg:{peer_id}")
    if not res:
        return None

    # Декодируем байты если нужно
    if isinstance(res, bytes):
        res = res.decode('utf-8')

    return extract_msg_id(res)

async def set_last_bot_msg(peer_id: int, cmid: int):
    """Запоминает CMID последнего сообщения бота"""
    clean_id = extract_msg_id(cmid)
    if clean_id:
        await redis_client.set(f"last_bot_msg:{peer_id}", str(clean_id), ex=86400)

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
    # Увеличенная задержка для стабильности Ghost Interface (Flood Control protection)
    await asyncio.sleep(0.45)

    if isinstance(keyboard, dict):
        keyboard = json.dumps(keyboard, ensure_ascii=False)

    # Если просят удалить последнее сообщение перед отправкой нового
    if delete_last and not conversation_message_id and not message_id:
        last_mid = await get_last_bot_msg(peer_id)
        if last_mid:
            await delete_bot_message(bot_api, peer_id, mid=last_mid)

    try:
        if conversation_message_id:
            try:
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
            except Exception as e:
                # Flood control (error 9)
                if "9" in str(e) or "Flood control" in str(e):
                    logger.warning(f"Flood control (CMID={conversation_message_id}), waiting 1.5s...")
                    await asyncio.sleep(1.5)
                    # Повторная попытка после паузы
                    await bot_api.messages.edit(
                        peer_id=peer_id,
                        message=message,
                        conversation_message_id=conversation_message_id,
                        keyboard=keyboard,
                        attachment=attachment,
                        **kwargs
                    )
                    return conversation_message_id

                # Если ошибка 15 (Access Denied) при использовании CMID, пробуем как message_id
                if "15" in str(e) or "Access denied" in str(e):
                    try:
                        await bot_api.messages.edit(
                            peer_id=peer_id,
                            message=message,
                            message_id=conversation_message_id,
                            keyboard=keyboard,
                            attachment=attachment,
                            **kwargs
                        )
                        return conversation_message_id
                    except VKAPIError[15]:
                        pass # Попробуем отправить новое ниже
                raise e
        elif message_id:
            try:
                await bot_api.messages.edit(
                    peer_id=peer_id,
                    message=message,
                    message_id=message_id,
                    keyboard=keyboard,
                    attachment=attachment,
                    **kwargs
                )
                return message_id
            except Exception as e:
                if "9" in str(e) or "Flood control" in str(e):
                    logger.warning(f"Flood control (MID={message_id}), waiting 1.5s...")
                    await asyncio.sleep(1.5)
                    # Повторная попытка
                    await bot_api.messages.edit(
                        peer_id=peer_id,
                        message=message,
                        message_id=message_id,
                        keyboard=keyboard,
                        attachment=attachment,
                        **kwargs
                    )
                    return message_id
                raise e
    except Exception as e:
        logger.warning(f"Ghost edit failed, attempting recovery: {e}")
        # Пробуем удалить старое сообщение обоими способами перед отправкой нового
        if conversation_message_id:
            await delete_bot_message(bot_api, peer_id, cmid=conversation_message_id)
            await delete_bot_message(bot_api, peer_id, mid=conversation_message_id)
        elif message_id:
            await delete_bot_message(bot_api, peer_id, mid=message_id)

    # Если редактирование не удалось или не запрашивалось, отправляем новое сообщение
    try:
        resp = await bot_api.messages.send(
            peer_id=peer_id,
            message=message,
            keyboard=keyboard,
            attachment=attachment,
            random_id=random.getrandbits(63),
            **kwargs
        )
    except VKAPIError[912]:
        logger.warning(f"Bot lacks permission to perform this action in chat (PeerID={peer_id})")
        return None
    except VKAPIError[7]:
        logger.warning(f"No permission to send message to {peer_id}")
        return None

    clean_resp_id = extract_msg_id(resp)
    if clean_resp_id:
        await set_last_bot_msg(peer_id, clean_resp_id)

    # Обновляем глобальный кэш тайпинга, если это было сообщение тайпинга
    if peer_id in _typing_msg_ids:
        _typing_msg_ids[peer_id] = clean_resp_id or resp

    return clean_resp_id or resp

async def send_temp_message(bot_api, peer_id: int, message: str, delay: int = 5, **kwargs):
    """Отправляет временное сообщение, которое удаляется через delay секунд"""
    try:
        try:
            mid = await bot_api.messages.send(peer_id=peer_id, message=message, random_id=random.getrandbits(63), **kwargs)
        except VKAPIError[912]:
            logger.warning(f"Bot lacks permission to perform this action in chat (PeerID={peer_id})")
            return None
        except VKAPIError[7]:
            logger.warning(f"No permission to send message to {peer_id}")
            return None

        async def _delete_after():
            await asyncio.sleep(delay)
            # В VK для удаления своего сообщения в ЛС часто нужны message_ids (mid)
            # а в беседах можно и CMID. Попробуем оба варианта через общую функцию.
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
        nonlocal conversation_message_id
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
                        try:
                            resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=random.getrandbits(63))
                            msg_id = extract_msg_id(resp) or resp
                        except VKAPIError[912]:
                            logger.warning(f"Bot lacks permission for dynamic typing in chat (PeerID={peer_id})")
                            return # Выходим из цикла если нет прав на бота
                        except VKAPIError[7]:
                            logger.warning(f"No permission for dynamic typing in {peer_id}")
                            return

                        _typing_msg_ids[peer_id] = msg_id
                        await set_last_bot_msg(peer_id, msg_id)
                    else:
                        try:
                            await asyncio.sleep(0.4) # Задержка перед edit в цикле

                            # Чистим ID перед использованием
                            clean_mid = extract_msg_id(msg_id)

                            # Если мы редактируем существующее сообщение по CMID
                            if conversation_message_id and clean_mid == conversation_message_id:
                                await bot_api.messages.edit(peer_id=peer_id, message=phrase, conversation_message_id=clean_mid)
                            else:
                                # Иначе по MID (message_id)
                                await bot_api.messages.edit(peer_id=peer_id, message=phrase, message_id=clean_mid)

                            await set_last_bot_msg(peer_id, clean_mid)
                        except Exception as edit_err:
                            if "9" in str(edit_err) or "Flood control" in str(edit_err):
                                logger.warning(f"Flood control in _typing_loop for {peer_id}, waiting 2s...")
                                await asyncio.sleep(2.0)
                            # Если не удалось отредактировать (например, сообщение удалено), шлем новое
                            logger.debug(f"Typing edit failed for {peer_id}, sending new: {edit_err}")
                            try:
                                resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=random.getrandbits(63))
                                msg_id = extract_msg_id(resp) or resp
                            except VKAPIError[912]:
                                logger.warning(f"Bot lacks permission for dynamic typing in chat (PeerID={peer_id}) during recovery")
                                return

                            # Важно: если мы перешли на новое сообщение, больше не используем старый conversation_message_id
                            if conversation_message_id == msg_id:
                                conversation_message_id = None

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
