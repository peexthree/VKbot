import os
import json
import datetime
import random
import textwrap
import asyncio
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Callback
from vkbottle.bot import BotLabeler, Message
from database import (
    get_user, set_user_state, save_feedback, update_user,
    get_unposted_feedbacks, mark_feedbacks_as_posted
)
from cache import get_temp_birth_data
from modules.bot_init import bot
from modules.utils import (
    ADMIN_ID, get_fsm_step, acquire_lock, release_lock,
    get_main_keyboard, ghost_edit, delete_bot_message, get_last_bot_msg
)
from modules.utils.consts import GROUP_ID
from modules.utils.photos import upload_wall_photo

labeler = BotLabeler()

# Маппинг секций для красивого вывода
SECTION_NAMES = {
    "money": "Денежный канал",
    "sex": "Сексуальность",
    "shadow": "Теневая матрица",
    "synastry": "Совместимость",
    "card_of_day": "Карта дня"
}

def create_neon_feedback_card(user_name: str, section_name: str, rating: int, comment: str, output_path: str):
    """Генерация стильной карточки отзыва через Pillow (Glassmorphism / Gothic Tech)"""
    width, height = 1200, 800

    # 1. Создание фона (Глубокий темный градиент с поддержкой альфа-канала для рисования)
    base = Image.new('RGBA', (width, height), (5, 2, 10, 255))
    draw = ImageDraw.Draw(base)

    # 2. Добавление неонового свечения (фоновые сферы)
    glow_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    # Рисуем размытые фиолетовые круги
    def draw_glow(d, x, y, r, color):
        d.ellipse([x-r, y-r, x+r, y+r], fill=color)

    draw_glow(glow_draw, 100, 100, 300, (80, 0, 150, 60))
    draw_glow(glow_draw, 1100, 700, 350, (40, 0, 100, 50))
    draw_glow(glow_draw, 600, 400, 200, (100, 50, 200, 30))

    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(80))
    base.paste(glow_layer, (0, 0), glow_layer)

    # 3. Стеклянная плашка (Glassmorphism effect)
    glass_margin = 80
    glass_rect = [glass_margin, glass_margin, width - glass_margin, height - glass_margin]

    # Рисуем полупрозрачную плашку
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(glass_rect, radius=40, fill=(20, 20, 30, 160), outline=(179, 136, 255, 40), width=2)
    base.paste(overlay, (0, 0), overlay)

    # 4. Рендеринг текста
    font_bold = "Lora-Bold.ttf"
    if not os.path.exists(font_bold): font_bold = "DejaVuSans-Bold.ttf"

    try:
        f_header = ImageFont.truetype(font_bold, 30)
        f_name = ImageFont.truetype(font_bold, 60)
        f_section = ImageFont.truetype(font_bold, 26)
        f_comment = ImageFont.truetype(font_bold, 38)
    except Exception:
        f_header = f_name = f_section = f_comment = ImageFont.load_default()

    # Заголовок
    draw.text((150, 130), "ФРАГМЕНТ МАТРИЦЫ: ОТЗЫВ", font=f_header, fill=(179, 136, 255, 200))

    # Имя
    draw.text((150, 180), user_name, font=f_name, fill=(255, 255, 255))

    # Направление
    draw.text((150, 260), f"КАНАЛ: {section_name.upper()}", font=f_section, fill=(170, 170, 170))

    # Рисуем звезды вектором с неоновым свечением
    start_x = 150
    start_y = 310
    star_size = 40
    gap = 15

    # 1. Создаем отдельный слой для размытого свечения звезд
    stars_glow_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    stars_glow_draw = ImageDraw.Draw(stars_glow_layer)
    stars_points = []

    for i in range(rating):
        cx = start_x + i * (star_size + gap) + star_size / 2
        cy = start_y + star_size / 2

        # Считаем точки для звезды
        points = []
        r_out = star_size / 2
        r_in = r_out * 0.4
        for j in range(10):
            r = r_out if j % 2 == 0 else r_in
            angle = j * 36 - 90
            rad = math.radians(angle)
            px = cx + r * math.cos(rad)
            py = cy + r * math.sin(rad)
            points.append((px, py))
        stars_points.append(points)

        # Рисуем основу для свечения на отдельном слое (чуть ярче и больше)
        points_glow = []
        r_out_g = r_out + 2
        r_in_g = r_out_g * 0.4
        for j in range(10):
            r = r_out_g if j % 2 == 0 else r_in_g
            angle = j * 36 - 90
            rad = math.radians(angle)
            px = cx + r * math.cos(rad)
            py = cy + r * math.sin(rad)
            points_glow.append((px, py))

        stars_glow_draw.polygon(points_glow, fill=(255, 170, 0, 180))

    # Размываем слой со свечением и накладываем на базу
    stars_glow_layer = stars_glow_layer.filter(ImageFilter.GaussianBlur(5))
    base.paste(stars_glow_layer, (0, 0), stars_glow_layer)

    # 2. Рисуем основные тела звезд поверх свечения
    for points in stars_points:
        draw.polygon(points, fill=(255, 215, 0, 255))

    # Комментарий с автопереносом
    wrapped_text = textwrap.fill(comment, width=45)
    # Отрисовка с кавычками
    final_comment_text = f"«{wrapped_text}»"
    draw.multiline_text((150, 420), final_comment_text, font=f_comment, fill=(230, 230, 230), spacing=15)

    # 5. Логотип
    logo_path = "cards/uslugi/logo.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo_w = 240
        w_percent = (logo_w / float(logo.size[0]))
        logo_h = int((float(logo.size[1]) * float(w_percent)))
        logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

        # Размещаем в правом нижнем углу плашки
        lx = width - glass_margin - logo_w - 50
        ly = height - glass_margin - logo_h - 40
        base.paste(logo, (lx, ly), logo)

    # Конвертируем обратно в RGB перед сохранением для оптимального размера и совместимости
    base = base.convert("RGB")
    base.save(output_path, "PNG")

async def send_feedback_to_chat(vk_id: int, section: str, rating: int, comment_text: str):
    """Сбор отзывов пачками по 4 штуки и публикация каруселью"""
    # Используем глобальную блокировку для предотвращения гонки при пакетной публикации
    if not await acquire_lock("batch_feedback_publish", ttl=60):
        return

    try:
        # Получаем список неопубликованных отзывов
        unposted = await get_unposted_feedbacks(limit=4)

        if len(unposted) < 4:
            logger.info(f"Feedback queue: {len(unposted)}/4. Waiting for more.")
            return

        logger.info("Feedback queue full (4/4). Starting batch publication...")

        attachments = []
        temp_files = []
        feedback_ids = []

        # 1. Генерация и загрузка карточек
        for f in unposted:
            f_id = f.get("id")
            u_id = f.get("user_id")
            sec = f.get("service_name")
            rat = f.get("rating")
            comm = f.get("comment") or "Без комментария"

            # Получаем имя пользователя
            user_data = await get_user(u_id)
            if user_data:
                full_name = f"{user_data.get('first_name', 'Адепт')} {user_data.get('last_name', '')}".strip() or "Адепт"
            else:
                full_name = "Адепт"

            sec_ru = SECTION_NAMES.get(sec, sec.capitalize())

            temp_filename = f"feedback_batch_{f_id}_{random.randint(1000, 9999)}.png"
            temp_path = os.path.join("cards", temp_filename)

            # Рендерим карточку
            create_neon_feedback_card(full_name, sec_ru, rat, comm, temp_path)
            temp_files.append(temp_path)
            feedback_ids.append(f_id)

            # Загружаем в ВК (upload_wall_photo ожидает относительный путь к файлу внутри 'cards/', либо просто имя файла)
            att = await upload_wall_photo(bot.api, temp_filename)
            if att:
                attachments.append(att)

            await asyncio.sleep(0.5) # Небольшая пауза между загрузками

        if not attachments:
            logger.error("Failed to upload feedback batch cards to VK")
            return

        # 2. Публикация поста
        post_text = (
            "💥 СИСТЕМА ФИКСИРУЕТ ТРАНСФОРМАЦИЮ: ПАКЕТ ОТЗЫВОВ 💥\n\n"
            "Матрица «Анти-Тар» меняет жизни в реальном времени. Свежая порция честной обратной связи от наших адептов, которые не побоялись заглянуть в свои коды судьбы. Листай карусель.\n\n"
            "Хочешь получить свой персональный разбор и взломать реальность? Нажми кнопку Написать сообществу под этим постом."
        )

        await bot.api.wall.post(
            owner_id=-GROUP_ID,
            from_group=1,
            message=post_text,
            attachments=",".join(attachments)
        )
        logger.success(f"Batch feedback post published successfully with {len(attachments)} cards")

        # 3. Обновление статуса в БД
        await mark_feedbacks_as_posted(feedback_ids)

        # 4. Очистка временных файлов
        for path in temp_files:
            if os.path.exists(path):
                os.remove(path)

    except Exception as e:
        logger.exception(f"Error in batch send_feedback_to_chat: {e}")
    finally:
        await release_lock("batch_feedback_publish")

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

@labeler.message(func=is_waiting_feedback_comment)
async def process_feedback_comment(message: Message):
    vk_id = message.from_id
    state = await get_fsm_step(vk_id)
    if not state: return

    rating, section = state.get("rating"), state.get("section")
    comment_text = message.text

    await save_feedback(vk_id, section, rating, comment=comment_text)

    # Публикация отзыва в группу (сработает при накоплении 4 штук)
    await send_feedback_to_chat(vk_id, section, rating, comment_text)

    await set_user_state(vk_id, "")

    # Удаляем сообщение с предложением оставить комментарий
    try:
        last_msg_id = await get_last_bot_msg(message.peer_id)
        if last_msg_id:
            await delete_bot_message(bot.api, message.peer_id, mid=last_msg_id)
    except Exception as e:
        logger.debug(f"Failed to delete rating comment prompt: {e}")

    kb = Keyboard(inline=True)
    kb.add(Callback("🔮 Новый расклад", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("🏠 Главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

    await message.answer(
        "Спасибо за обратную связь! Твой вклад помогает системе эволюционировать.",
        keyboard=kb.get_json()
    )

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
