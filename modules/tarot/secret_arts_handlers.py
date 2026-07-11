import random
import asyncio
from vkbottle.bot import BotLabeler, Message

from database import set_user_state
from modules.bot_init import bot
from modules.utils import acquire_lock, release_lock, extract_msg_id, get_fsm_step
from modules.payments.logic import execute_generation

labeler = BotLabeler()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def _is_text_valid_for_fsm(message: Message) -> bool:
    if not message.text: return False
    # Игнорируем меню и навигацию
    if any(message.text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "👤", "🎴", "⚙️", "✅", "🔄", "✨", "🕸", "📜", "✒", "⚡️", "📢"]): return False
    if message.text.lower() in ["начать", "start", "/start", "главное меню", "профиль", "услуги", "гримуар", "тайные искусства"]: return False
    return True


async def is_waiting_oculomancy_photo(message: Message) -> bool:
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_oculomancy_photo"


async def is_waiting_sigil_wish(message: Message) -> bool:
    if not await _is_text_valid_for_fsm(message): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_sigil_wish"


async def is_waiting_geo_location(message: Message) -> bool:
    if not await _is_text_valid_for_fsm(message): return False
    state_dict = await get_fsm_step(message.from_id)
    return state_dict is not None and state_dict.get("step") == "waiting_geo_location"


# --- 👁 ОКУЛОМАНТИЯ: ОЖИДАНИЕ ФОТО ГЛАЗА ---
@labeler.message(func=is_waiting_oculomancy_photo)
async def process_oculomancy_photo(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        photos = []
        if message.attachments:
            for att in message.attachments:
                if att.photo:
                    sizes = att.photo.sizes
                    max_size = max(sizes, key=lambda s: s.width * s.height)
                    photos.append(max_size.url)

        if not photos:
            if message.text and message.text.lower() in ["начать", "главное меню", "тайные искусства"]:
                await set_user_state(vk_id, "")
                from modules.keyboards import secret_arts_menu_kb
                await message.answer("Возвращаюсь в Тайные Искусства... ✨", keyboard=secret_arts_menu_kb())
                return
            await message.answer("Пожалуйста, отправьте именно фотографию вашего глаза крупным планом.")
            return

        # Берем первое фото глаза
        eye_photo_url = photos[0]
        await set_user_state(vk_id, "")

        # Сохраняем в Redis
        from cache import redis_client
        await redis_client.set(f"oculomancy_photo:{vk_id}", eye_photo_url, ex=600)

        # Сообщаем о начале ритуала
        resp = await bot.api.messages.send(
            peer_id=message.peer_id,
            message="✦ ФОТО КАНАЛА ПРИНЯТО. ОЧИЩАЮ ЗЕРКАЛО ДУШИ...",
            random_id=random.getrandbits(63)
        )
        conv_id = extract_msg_id(resp)

        # Запускаем генерацию
        asyncio.create_task(execute_generation(
            vk_id=vk_id,
            peer_id=message.peer_id,
            target_section="oculomancy",
            partner_name="",
            partner_date="",
            conversation_message_id=conv_id
        ))
    finally:
        await release_lock(vk_id)


# --- 🎨 СИГИЛ-МАСТЕР: ОЖИДАНИЕ ЖЕЛАНИЯ ---
@labeler.message(func=is_waiting_sigil_wish)
async def process_sigil_wish(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        wish_text = message.text.strip() if message.text else ""
        if len(wish_text) < 5:
            await message.answer("Пожалуйста, опиши свое желание более осознанно (хотя бы одно предложение), чтобы я смогла начертить точный глиф.")
            return

        await set_user_state(vk_id, "")

        # Сохраняем желание в Redis
        from cache import redis_client
        await redis_client.set(f"sigil_wish:{vk_id}", wish_text, ex=600)

        # Сообщаем о начале ритуала
        resp = await bot.api.messages.send(
            peer_id=message.peer_id,
            message="✦ НАМЕРЕНИЕ ПРИНЯТО. НАЧИНАЮ СВЕДЕНИЕ ЛИНИЙ И ГЛИФОВ...",
            random_id=random.getrandbits(63)
        )
        conv_id = extract_msg_id(resp)

        # Запускаем генерацию
        asyncio.create_task(execute_generation(
            vk_id=vk_id,
            peer_id=message.peer_id,
            target_section="sigil",
            partner_name="",
            partner_date="",
            conversation_message_id=conv_id
        ))
    finally:
        await release_lock(vk_id)


# --- 🗺 АСТРО-КАРТОГРАФИЯ: ОЖИДАНИЕ ГЕОЛОКАЦИИ ---
@labeler.message(func=is_waiting_geo_location)
async def process_geo_location(message: Message):
    vk_id = message.from_id
    if not await acquire_lock(vk_id): return
    try:
        location_text = message.text.strip() if message.text else ""
        await set_user_state(vk_id, "")

        # Сохраняем локацию в Redis
        from cache import redis_client
        await redis_client.set(f"astro_geo_loc:{vk_id}", location_text, ex=600)

        # Сообщаем о начале ритуала
        resp = await bot.api.messages.send(
            peer_id=message.peer_id,
            message="✦ КООРДИНАТЫ ПРИНЯТЫ. НАКЛАДЫВАЮ СЕТКУ АСТРО-ЛИНИЙ НА ГЕОГРАФИЮ...",
            random_id=random.getrandbits(63)
        )
        conv_id = extract_msg_id(resp)

        # Запускаем генерацию
        asyncio.create_task(execute_generation(
            vk_id=vk_id,
            peer_id=message.peer_id,
            target_section="astro_geo",
            partner_name="",
            partner_date="",
            conversation_message_id=conv_id
        ))
    finally:
        await release_lock(vk_id)
