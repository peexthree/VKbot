import json
import random
from vkbottle import Keyboard, Callback, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message
from database import set_user_state
from modules.utils import get_fsm_step, acquire_lock, release_lock
from modules.states import MyStates
from .daily import card_of_day_logic

labeler = BotLabeler()

async def is_waiting_oracle_cut(message: Message) -> bool:
    if message.text:
        if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
        if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар"]: return False
    state = await get_fsm_step(message.from_id)
    return state is not None and state.get("step") == "oracle_cut"

@labeler.message(func=is_waiting_oracle_cut)
async def process_oracle_cut_handler(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        state = await get_fsm_step(vk_id)
        pool = list(range(0, 78))
        random.shuffle(pool)
        pool = pool[:10]
        await set_user_state(vk_id, json.dumps({"step": "oracle_draw", "question": state.get("question", ""), "drawn_cards": [], "pool": pool}))
        kb = Keyboard(inline=True)
        for i, cid in enumerate(pool):
            kb.add(Callback("🎴", payload={"oracle_card": cid}))
            kb.row()
        await message.answer("ШАГ 3 ИЗ 3: ВЫБОР КАРТ. Выбери из своей стопки ровно 3 карты", keyboard=kb.get_json())
    finally: await release_lock(vk_id)

@labeler.message(text=["Карта дня", "✦ Карта дня", "🃏 Карта дня", "🃏 КАРТА ДНЯ"])
async def card_of_day_handler(message: Message):
    await card_of_day_logic(message.from_id, message.peer_id, conversation_message_id=message.conversation_message_id)

@labeler.message(state=MyStates.WAITING_ORACLE_QUESTION)
async def process_oracle_question(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        await set_user_state(vk_id, json.dumps({"step": "oracle_cut", "question": message.text.strip()}))
        kb = Keyboard(inline=True).add(Callback("✦ ОБРЕЗАТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.PRIMARY)
        await message.answer("ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже, чтобы обрезать колоду", keyboard=kb.get_json())
    finally: await release_lock(vk_id)
