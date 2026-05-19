import json
import datetime
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from vkbottle.bot import BotLabeler, Message
from database import get_user, set_user_state
from modules.bot_init import bot
from modules.utils import ADMIN_ID, get_fsm_step, acquire_lock, release_lock
from modules.states import MyStates

labeler = BotLabeler()

async def support_handler_logic(vk_id: int, peer_id: int, conversation_message_id: int = None):
    """Инициализация обращения в поддержку"""
    await set_user_state(vk_id, "waiting_support_question")

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

@labeler.message(state=MyStates.WAITING_SUPPORT_QUESTION)
async def process_support_question(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(f"support_{vk_id}"): return

    try:
        user = await get_user(vk_id)
        u_name = "Адепт"
        u_city = "Неизвестно"
        if user:
            u_name = f"{user.get('first_name', 'Адепт')} {user.get('last_name', '')}".strip()
            u_city = user.get("birth_city", "Неизвестно")

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

        await bot.api.messages.send(peer_id=ADMIN_ID, message=admin_msg, keyboard=kb.get_json(), random_id=0)

        # Сбрасываем стейт
        await set_user_state(vk_id, "")

        await message.answer("✅ Твой вопрос отправлен. Ожидай ответа от техподдержки в ближайшее время.")

    except Exception as e:
        logger.error(f"Error in process_support_question: {e}")
        await message.answer("❌ Произошла ошибка при отправке вопроса. Попробуй позже.")
    finally:
        await release_lock(f"support_{vk_id}")

# --- Админские функции ---

async def admin_reply_start_logic(admin_id: int, user_id: int):
    """Админ нажал 'Ответить'"""
    if admin_id != ADMIN_ID: return

    await set_user_state(admin_id, json.dumps({"step": "waiting_admin_reply", "target_user_id": user_id}))
    await bot.api.messages.send(peer_id=admin_id, message=f"Напиши текст ответа для пользователя {user_id}:", random_id=0)

@labeler.message(func=lambda m: m.from_id == ADMIN_ID)
async def process_admin_reply(message: Message):
    state = await get_fsm_step(ADMIN_ID)
    if not state or state.get("step") != "waiting_admin_reply":
        return
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
        await bot.api.messages.send(peer_id=target_user_id, message=user_msg, random_id=0)
        await message.answer(f"✅ Ответ успешно отправлен пользователю {target_user_id}.")
    except Exception as e:
        logger.error(f"Failed to send reply to {target_user_id}: {e}")
        await message.answer(f"❌ Не удалось отправить ответ: {e}")

    await set_user_state(ADMIN_ID, "")
