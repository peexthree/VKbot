import re

with open('modules/utils/ui.py', 'r') as f:
    content = f.read()

# Modify ghost_edit to add short delay and catch Flood Control
new_ghost_edit = """async def ghost_edit(
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
    await asyncio.sleep(0.4) # Add reasonable delay to prevent flood control

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
                    logger.warning(f"Flood control in ghost_edit (CMID), waiting 1.5s...")
                    await asyncio.sleep(1.5)
                    raise e
                # Если ошибка 15 (Access Denied) при использовании CMID, пробуем как message_id
                if "15" in str(e) or "Access denied" in str(e):
                    await bot_api.messages.edit(
                        peer_id=peer_id,
                        message=message,
                        message_id=conversation_message_id,
                        keyboard=keyboard,
                        attachment=attachment,
                        **kwargs
                    )
                    return conversation_message_id
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
                    logger.warning(f"Flood control in ghost_edit (MID), waiting 1.5s...")
                    await asyncio.sleep(1.5)
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
    resp = await bot_api.messages.send(
        peer_id=peer_id,
        message=message,
        keyboard=keyboard,
        attachment=attachment,
        random_id=random.getrandbits(63),
        **kwargs
    )

    # Пытаемся сохранить как последнее
    if isinstance(resp, int):
        await set_last_bot_msg(peer_id, resp)
    elif isinstance(resp, dict) and "conversation_message_id" in resp:
        await set_last_bot_msg(peer_id, resp["conversation_message_id"])
    elif isinstance(resp, str) and "conversation_message_id=" in resp:
        try:
            val = resp.split("conversation_message_id=")[1].split()[0]
            await set_last_bot_msg(peer_id, int(val))
        except: pass

    # Обновляем глобальный кэш тайпинга, если это было сообщение тайпинга
    if peer_id in _typing_msg_ids:
        _typing_msg_ids[peer_id] = resp

    return resp
"""

content = re.sub(r'async def ghost_edit\(.*?\n    return resp\n', new_ghost_edit, content, flags=re.DOTALL)

# Modify _typing_loop to add Flood Control catch
new_typing_loop = """            while True:
                try:
                    available_phrases = [p for p in THEATRICAL_PHRASES if p != last_phrase]
                    phrase = random.choice(available_phrases) if available_phrases else random.choice(THEATRICAL_PHRASES)
                    last_phrase = phrase

                    if msg_id is None:
                        resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=random.getrandbits(63))
                        msg_id = resp
                        _typing_msg_ids[peer_id] = msg_id
                        await set_last_bot_msg(peer_id, msg_id)
                    else:
                        try:
                            # Если мы редактируем существующее сообщение по CMID
                            if conversation_message_id and msg_id == conversation_message_id:
                                await bot_api.messages.edit(peer_id=peer_id, message=phrase, conversation_message_id=msg_id)
                            else:
                                # Иначе по MID (message_id)
                                await bot_api.messages.edit(peer_id=peer_id, message=phrase, message_id=msg_id)
                            await set_last_bot_msg(peer_id, msg_id)
                        except Exception as edit_err:
                            if "9" in str(edit_err) or "Flood control" in str(edit_err):
                                logger.warning(f"Flood control in _typing_loop, waiting 2s...")
                                await asyncio.sleep(2.0)
                            # Если не удалось отредактировать (например, сообщение удалено), шлем новое
                            logger.debug(f"Typing edit failed, sending new: {edit_err}")
                            resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=random.getrandbits(63))
                            msg_id = resp
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
                await asyncio.sleep(4)"""

content = re.sub(r'            while True:\n                try:.*?await asyncio\.sleep\(4\)', new_typing_loop, content, flags=re.DOTALL)

with open('modules/utils/ui.py', 'w') as f:
    f.write(content)
