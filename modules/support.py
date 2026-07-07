import json
import datetime
import random
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from vkbottle.bot import BotLabeler, Message
from database import get_user, set_user_state
from modules.bot_init import bot
from modules.utils import ADMIN_ID, get_fsm_step, acquire_lock, release_lock, get_main_keyboard

labeler = BotLabeler()

async def support_handler_logic(vk_id: int, peer_id: int, conversation_message_id: int = None):
    """Инициализация обращения в поддержку"""
    await set_user_state(vk_id, json.dumps({"step": "waiting_support_question"}))

    text = (
        "📞 ТЕХНИЧЕСКАЯ ПОДДЕРЖКА\n\n"
        "Напиши свой вопрос или опиши проблему прямо здесь. "
        "Я сразу передам его разработчику.\n\n"
        "Если передумал — просто нажми кнопку ниже."
    )

    kb = Keyboard(inline=True)
    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

    from modules.utils import ghost_edit
    await ghost_edit(
        bot.api,
        peer_id,
        text,
        conversation_message_id=conversation_message_id,
        keyboard=kb.get_json()
    )

async def is_waiting_support_question(message: Message) -> bool:
    if not message.text: return False
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар"]: return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_support_question"

async def is_waiting_feedback_comment(message: Message) -> bool:
    if not message.text: return False
    if message.text.lower() in ["начать", "start", "/start", "главное меню"]: return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_feedback_comment"

async def send_feedback_to_chat(vk_id: int, section: str, rating: int, comment_text: str):
    """Вспомогательная функция для отправки отзыва в чат"""
    import os
    peer_id = os.environ.get("VK_FEEDBACK_PEER_ID")
    if not peer_id:
        return

    try:
        user = await get_user(vk_id)
        name = user.get("first_name", "Адепт") if user else "Адепт"
        msg = (
            "АНТИ-ТАР: НОВЫЙ ОТЗЫВ\n"
            f"• Адепт: [id{vk_id}|{name}]\n"
            f"• Прогноз: {section}\n"
            f"• Оценка: {rating} / 5\n"
            f"• Комментарий: {comment_text}"
        )
        # Возвращаем прямую отправку на peer_id (например, 2000000130)
        final_peer_id = int(peer_id)
        await bot.api.messages.send(peer_id=final_peer_id, message=msg, random_id=random.getrandbits(63))
    except Exception as e:
        logger.error(f"Error sending feedback to chat: {e}")

@labeler.message(func=is_waiting_feedback_comment)
async def process_feedback_comment(message: Message):
    vk_id = message.from_id
    state = await get_fsm_step(vk_id)
    if not state: return

    rating, section = state.get("rating"), state.get("section")
    comment_text = message.text

    from database import save_feedback
    await save_feedback(vk_id, section, rating, comment=comment_text)

    # Отправка в чат ВК
    await send_feedback_to_chat(vk_id, section, rating, comment_text)

    await set_user_state(vk_id, "")
    await message.answer("Спасибо за обратную связь! Твой вклад помогает системе эволюционировать.", keyboard=get_main_keyboard(vk_id))

@labeler.message(func=is_waiting_support_question)
async def process_support_question(message: Message):
    vk_id = message.from_id

    if message.text.lower() in ["отмена", "назад", "cancel"]:
        await set_user_state(vk_id, "")
        await bot.api.messages.send(
            peer_id=message.peer_id,
            message="Связь прервана. Возвращаюсь в главное меню.",
            keyboard=get_main_keyboard(vk_id),
            random_id=random.getrandbits(63)
        )
        return

    if not await acquire_lock(f"support_{vk_id}"): return

    try:
        user = await get_user(vk_id)
        u_name = "Адепт"
        u_city = "Неизвестно"
        if user:
            u_name = f"{user.get('first_name', 'Адепт')} {user.get('last_name', '')}".strip()
            # Пробуем достать город из Redis
            from cache import get_temp_birth_data
            temp_birth = await get_temp_birth_data(vk_id)
            if temp_birth and temp_birth.get("city"):
                u_city = temp_birth.get("city")

        question_text = message.text

        # Сохраняем в историю поддержки
        support_history = user.get("support_history", []) if user else []
        support_history.append({
            "role": "user",
            "text": question_text,
            "date": datetime.datetime.now().isoformat()
        })
        from database import update_user
        await update_user(vk_id, {"support_history": support_history})

        # Уведомляем админа
        admin_msg = (
            f"🆘 НОВЫЙ ВОПРОС ПОДДЕРЖКИ\n"
            f"От: {u_name} (ID: {vk_id})\n"
            f"Город: {u_city}\n\n"
            f"ТЕКСТ:\n{question_text}"
        )

        kb = Keyboard(inline=True)
        kb.add(Callback("📝 ОТВЕТИТЬ", payload={"cmd": "admin_reply_start", "user_id": vk_id}), color=KeyboardButtonColor.POSITIVE)

        logger.info(f"Sending support question from {vk_id} to admin {ADMIN_ID}")
        res = await bot.api.messages.send(peer_id=ADMIN_ID, message=admin_msg, keyboard=kb.get_json(), random_id=random.getrandbits(63))
        logger.info(f"Support message sent to admin. Result: {res}")

        # Сбрасываем стейт
        await set_user_state(vk_id, "")

        await message.answer("✅ Твой вопрос отправлен. Ожидай ответа от техподдержки в ближайшее время.")

    except Exception as e:
        logger.exception(f"Error in process_support_question: {e}")
        await message.answer("❌ Произошла ошибка при отправке вопроса. Попробуй позже.")
    finally:
        await release_lock(f"support_{vk_id}")

# --- Админские функции ---

async def admin_reply_start_logic(admin_id: int, user_id: int):
    """Админ нажал 'Ответить'"""
    if admin_id != ADMIN_ID:
        logger.warning(f"Unauthorized admin access attempt by {admin_id}")
        return

    if not user_id:
        logger.error("admin_reply_start_logic: user_id is missing")
        return

    await set_user_state(admin_id, json.dumps({"step": "waiting_admin_reply", "target_user_id": user_id}))
    await bot.api.messages.send(peer_id=admin_id, message=f"Напиши текст ответа для пользователя {user_id}:", random_id=random.getrandbits(63))

async def is_waiting_admin_reply(message: Message) -> bool:
    if message.from_id != ADMIN_ID: return False
    if not message.text: return False
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    state_dict = await get_fsm_step(ADMIN_ID)
    return state_dict is not None and state_dict.get("step") == "waiting_admin_reply"

@labeler.message(func=is_waiting_admin_reply)
async def process_admin_reply(message: Message):
    state = await get_fsm_step(ADMIN_ID)
    target_user_id = state.get("target_user_id")

    if not target_user_id:
        await message.answer("Ошибка: не указан получатель.")
        await set_user_state(ADMIN_ID, "")
        return

    reply_text = message.text

    # Сохраняем в историю поддержки пользователя
    target_user = await get_user(target_user_id)
    if target_user:
        support_history = target_user.get("support_history", [])
        support_history.append({
            "role": "admin",
            "text": reply_text,
            "date": datetime.datetime.now().isoformat()
        })
        from database import update_user
        await update_user(target_user_id, {"support_history": support_history})

    user_msg = (
        "📨 ОТВЕТ ОТ ТЕХПОДДЕРЖКИ\n\n"
        f"{reply_text}\n\n"
        "Если у тебя остались вопросы, ты можешь задать их снова через меню Настройки."
    )

    try:
        await bot.api.messages.send(peer_id=target_user_id, message=user_msg, random_id=random.getrandbits(63))
        await message.answer(f"✅ Ответ успешно отправлен пользователю {target_user_id}.")
    except Exception as e:
        logger.error(f"Failed to send reply to {target_user_id}: {e}")
        await message.answer(f"❌ Не удалось отправить ответ: {e}")

    await set_user_state(ADMIN_ID, "")
