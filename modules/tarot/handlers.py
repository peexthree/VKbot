import json
from vkbottle import Keyboard, Callback, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message
from database import set_user_state
from modules.utils import get_fsm_step, acquire_lock, release_lock
from .daily import card_of_day_logic

labeler = BotLabeler()

async def is_waiting_oracle_question(message: Message) -> bool:
    if message.text:
        if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
        if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар", "админ панель"]: return False
    state = await get_fsm_step(message.from_id)
    return state is not None and state.get("step") == "waiting_oracle_question"

# Сначала регистрируем обработчики состояний, чтобы они имели приоритет
@labeler.message(func=is_waiting_oracle_question)
async def process_oracle_question(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        await set_user_state(vk_id, json.dumps({"step": "oracle_cut", "question": message.text.strip()}))
        kb = Keyboard(inline=True).add(Callback("✦ ОБРЕЗАТЬ КОЛОДУ", payload={"cmd": "oracle_cut"}), color=KeyboardButtonColor.PRIMARY)
        await message.answer("✨ ШАГ 2 ИЗ 3: СОПРИКОСНОВЕНИЕ ✨\nКоснись колоды, чтобы она почувствовала твое присутствие.", keyboard=kb.get_json())
    finally: await release_lock(vk_id)


# Общие команды
@labeler.message(func=lambda m: m.text and m.text.lower() in ['карта дня', '✦ карта дня', '🃏 карта дня'] and not m.attachments)
async def card_of_day_handler(message: Message):
    await card_of_day_logic(message.from_id, message.peer_id, conversation_message_id=message.conversation_message_id)
