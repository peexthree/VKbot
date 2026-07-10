import os
import json
import datetime
import random
import asyncio
import math
import io
import aiohttp
from typing import Optional
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
from modules.utils.consts import GROUP_ID, SKIN_VISUALS
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

def resolve_skin_path(skin_file: str) -> Optional[str]:
    """Разрешение пути к изображению проводника (в cards/uslugi/ или cards/)"""
    path1 = os.path.join("cards", "uslugi", skin_file)
    if os.path.exists(path1):
        return path1
    path2 = os.path.join("cards", skin_file)
    if os.path.exists(path2):
        return path2
    return None

def draw_gradient_text(draw, position, text, font, color_start, color_end, base_image):
    """Отрисовка красивого градиентного текста"""
    try:
        bbox = font.getbbox(text)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
    except Exception:
        # Резервный вариант для старых версий Pillow
        w, h = draw.textsize(text, font=font)

    if w <= 0 or h <= 0:
        return

    # Создаем маску с отступами
    text_mask = Image.new('L', (w + 20, h + 20), 0)
    mask_draw = ImageDraw.Draw(text_mask)
    mask_draw.text((10, 10), text, fill=255, font=font)

    # Создаем градиентную заливку
    gradient = Image.new('RGBA', (w + 20, h + 20))
    g_draw = ImageDraw.Draw(gradient)
    for x in range(w + 20):
        t = x / float(w + 20)
        r = int(color_start[0] + (color_end[0] - color_start[0]) * t)
        g = int(color_start[1] + (color_end[1] - color_start[1]) * t)
        b = int(color_start[2] + (color_end[2] - color_start[2]) * t)
        a = int(color_start[3] + (color_end[3] - color_start[3]) * t)
        g_draw.line([(x, 0), (x, h + 20)], fill=(r, g, b, a))

    pos_x = position[0] - 10
    pos_y = position[1] - 10
    base_image.paste(gradient, (pos_x, pos_y), text_mask)

def draw_glass_plate(base_image, rect, radius=30, fill_color=(20, 20, 30, 130), border_color=(179, 136, 255, 60)):
    """Рисование полупрозрачной размытой хрустальной плашки (эффект Glassmorphism)"""
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    cropped = base_image.crop((x0, y0, x1, y1))
    blurred = cropped.filter(ImageFilter.GaussianBlur(15))

    mask = Image.new('L', (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)

    tint = Image.new('RGBA', (w, h), fill_color)
    blurred.paste(tint, (0, 0), tint)

    base_image.paste(blurred, (x0, y0), mask)

    draw = ImageDraw.Draw(base_image)
    draw.rounded_rectangle(rect, radius=radius, outline=border_color, width=2)

def crop_to_circle_with_border(img, size=(100, 100), border_color=(179, 136, 255, 255), border_width=3, glow_color=(179, 136, 255, 100)):
    """Круговое кадрирование изображения с добавлением светящейся неоновой рамки"""
    img = img.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    w, h = size

    mask = Image.new('L', size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse([0, 0, w, h], fill=255)

    output = Image.new('RGBA', size, (0, 0, 0, 0))
    output.paste(img, (0, 0), mask)

    glow_size = (w + 10, h + 10)
    glow_layer = Image.new('RGBA', glow_size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gd.ellipse([2, 2, w + 8, h + 8], outline=glow_color, width=border_width + 2)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(3))

    final_img = Image.new('RGBA', glow_size, (0, 0, 0, 0))
    final_img.paste(glow_layer, (0, 0), glow_layer)
    final_img.paste(output, (5, 5), output)

    fd = ImageDraw.Draw(final_img)
    fd.ellipse([5, 5, w + 5, h + 5], outline=border_color, width=border_width)

    return final_img

def create_avatar_placeholder(first_letter: str, size=(110, 110), font_path="Lora-Bold.ttf"):
    """Создание заглушки для аватара с красивым космическим градиентом"""
    w, h = size
    nebula = Image.new('RGBA', size, (0, 0, 0, 0))
    nd = ImageDraw.Draw(nebula)
    nd.ellipse([0, 0, w, h], fill=(30, 20, 50, 255))
    nd.ellipse([w//4, h//4, w, h], fill=(142, 68, 173, 180))
    nd.ellipse([0, 0, w//2, h//2], fill=(41, 128, 185, 180))

    nebula = nebula.filter(ImageFilter.GaussianBlur(10))

    mask = Image.new('L', size, 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, w, h], fill=255)

    circle_bg = Image.new('RGBA', size, (0, 0, 0, 0))
    circle_bg.paste(nebula, (0, 0), mask)

    try:
        font = ImageFont.truetype(font_path, int(w * 0.5))
    except Exception:
        font = ImageFont.load_default()

    cd = ImageDraw.Draw(circle_bg)
    try:
        tb = font.getbbox(first_letter)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
    except Exception:
        tw, th = cd.textsize(first_letter, font=font)

    tx = (w - tw) // 2
    ty = (h - th) // 2 - 5
    cd.text((tx, ty), first_letter, fill=(255, 215, 0, 255), font=font)

    # Тонкая светящаяся фиолетовая рамка вокруг заглушки
    cd.ellipse([1, 1, w - 2, h - 2], outline=(179, 136, 255, 255), width=2)

    return circle_bg

def wrap_text_by_pixels(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Разбивка текста на строки по ширине в пикселях"""
    lines = []
    words = text.split()
    if not words:
        return []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            width = font.getlength(test_line)
        except AttributeError:
            try:
                width = font.getbbox(test_line)[2]
            except Exception:
                width = len(test_line) * (font.size * 0.5)

        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def create_neon_feedback_card(
    user_name: str,
    section_name: str,
    rating: int,
    comment: str,
    output_path: str,
    user_avatar_bytes: Optional[bytes] = None,
    active_skin: str = "olesya",
    feedback_id: Optional[int] = None,
    created_at: Optional[str] = None
):
    """Генерация стильной карточки отзыва через Pillow (Sacred Esotericism / Cosmos / Glassmorphism)"""
    width, height = 1200, 800

    # 1. Создание фона (Глубокий темный градиент)
    base = Image.new('RGBA', (width, height), (5, 2, 12, 255))
    draw = ImageDraw.Draw(base)

    # 2. Добавление мягкого астрального свечения (фоновые сферы)
    glow_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    def draw_glow(d, x, y, r, color):
        d.ellipse([x-r, y-r, x+r, y+r], fill=color)

    # Мягкие, глубокие туманности
    draw_glow(glow_draw, 150, 150, 350, (110, 0, 200, 50)) # Purple
    draw_glow(glow_draw, 1050, 650, 400, (30, 80, 180, 55)) # Cosmic Blue
    draw_glow(glow_draw, 600, 400, 250, (140, 50, 210, 35)) # Deep Indigo

    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(90))
    base.paste(glow_layer, (0, 0), glow_layer)

    # 3. Внешняя стеклянная плашка (Glassmorphism effect)
    glass_margin = 80
    glass_rect = [glass_margin, glass_margin, width - glass_margin, height - glass_margin]

    # Рисуем внешнюю плашку с матовым размытием и тонким светящимся неоновым контуром
    draw_glass_plate(base, glass_rect, radius=40, fill_color=(15, 10, 25, 150), border_color=(179, 136, 255, 50))

    # 4. Рендеринг шрифтов
    font_bold = "Lora-Bold.ttf"
    font_regular = "Lora-Regular.ttf"
    if not os.path.exists(font_bold): font_bold = "DejaVuSans-Bold.ttf"
    if not os.path.exists(font_regular): font_regular = "DejaVuSans.ttf"

    try:
        f_header = ImageFont.truetype(font_bold, 24)
        f_name = ImageFont.truetype(font_bold, 44)
        f_section = ImageFont.truetype(font_regular, 22)
        f_meta = ImageFont.truetype(font_regular, 16)
    except Exception:
        f_header = f_name = f_section = f_meta = ImageFont.load_default()

    # 5. Обработка и вставка аватара пользователя (слева от имени)
    avatar_size = 110
    avatar_x = 120
    avatar_y = 110

    if user_avatar_bytes:
        try:
            user_img = Image.open(io.BytesIO(user_avatar_bytes))
            user_avatar = crop_to_circle_with_border(user_img, size=(avatar_size, avatar_size), border_color=(179, 136, 255, 255), border_width=2, glow_color=(179, 136, 255, 90))
            base.paste(user_avatar, (avatar_x - 5, avatar_y - 5), user_avatar)
        except Exception as e:
            logger.error(f"Error processing user avatar image: {e}")
            user_avatar_bytes = None

    if not user_avatar_bytes:
        first_letter = user_name[0].upper() if user_name else "A"
        placeholder = create_avatar_placeholder(first_letter, size=(avatar_size, avatar_size), font_path=font_bold)
        base.paste(placeholder, (avatar_x, avatar_y), placeholder)

    # 6. Имя пользователя с космическим градиентом
    name_x = 250
    name_y = 110
    draw_gradient_text(
        draw,
        (name_x, name_y),
        user_name,
        f_name,
        color_start=(142, 68, 173, 255), # Deep amethyst
        color_end=(52, 152, 219, 255),   # Celestial blue
        base_image=base
    )

    # 7. Направление/Раздел (под именем)
    draw.text((name_x, 175), f"КАНАЛ: {section_name.upper()}", font=f_section, fill=(180, 185, 210, 210))

    # 8. Звезды рейтинга (Векторные звезды с красивым мягким свечением)
    start_x = 120
    start_y = 245
    star_size = 36
    gap = 12

    # Создаем отдельный слой для размытого свечения звезд (золотой/янтарный неон)
    stars_glow_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    stars_glow_draw = ImageDraw.Draw(stars_glow_layer)
    stars_points = []

    for i in range(rating):
        cx = start_x + i * (star_size + gap) + star_size / 2
        cy = start_y + star_size / 2

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

        points_glow = []
        r_out_g = r_out + 3
        r_in_g = r_out_g * 0.4
        for j in range(10):
            r = r_out_g if j % 2 == 0 else r_in_g
            angle = j * 36 - 90
            rad = math.radians(angle)
            px = cx + r * math.cos(rad)
            py = cy + r * math.sin(rad)
            points_glow.append((px, py))

        stars_glow_draw.polygon(points_glow, fill=(255, 190, 40, 150))

    stars_glow_layer = stars_glow_layer.filter(ImageFilter.GaussianBlur(4))
    base.paste(stars_glow_layer, (0, 0), stars_glow_layer)

    # Рисуем основные тела звезд поверх свечения
    for points in stars_points:
        draw.polygon(points, fill=(255, 215, 0, 255))

    # 9. Хрустальная подложка под отзыв (Inner glass plate)
    # Координаты: x: 120 to 930 (ширина 810). Оставшиеся 930-1080 для проводника в нижнем углу!
    comment_box_rect = [120, 310, 930, 640]
    draw_glass_plate(base, comment_box_rect, radius=25, fill_color=(10, 5, 20, 100), border_color=(255, 255, 255, 25))

    # 10. Текст отзыва с динамическим размером шрифта
    # Границы текста внутри хрустальной подложки
    text_x_start = 145
    text_y_start = 335
    text_max_width = 740  # 930 - 120 - 2*25-10
    text_max_height = 250 # 640 - 310 - 2*25+20

    # Лимит текста 280 символов для картинки (обрезаем до 280-го символа и дорисовываем троеточие)
    display_comment = comment.strip()
    if len(display_comment) > 280:
        display_comment = display_comment[:280].strip()
        if not display_comment.endswith("..."):
            display_comment += "..."

    # Алгоритм подбора размера шрифта
    comment_font_size = 32
    lines = []

    while comment_font_size > 18:
        try:
            f_comment = ImageFont.truetype(font_regular, comment_font_size)
        except Exception:
            f_comment = ImageFont.load_default()
            break

        lines = wrap_text_by_pixels(display_comment, f_comment, text_max_width)
        line_height = comment_font_size + 10
        total_height = len(lines) * line_height

        # Нам нужен нижний отступ минимум в 45 пикселей до границы
        if total_height + 45 <= text_max_height:
            break
        comment_font_size -= 2

    # Рендерим строки текста
    try:
        f_comment = ImageFont.truetype(font_regular, comment_font_size)
    except Exception:
        f_comment = ImageFont.load_default()

    line_height = comment_font_size + 10
    for idx, line in enumerate(lines):
        draw.text((text_x_start, text_y_start + idx * line_height), line, font=f_comment, fill=(240, 240, 250, 240))

    # 11. Астрологические метаданные на холсте
    if not feedback_id:
        feedback_id = random.randint(10000, 99999)
    if not created_at:
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        try:
            # Форматируем в удобочитаемый вид
            dt = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            created_at = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass

    status_options = ["STATUS: SYNCHRONIZED", "ENERGY: ALIGNED", "SPECTRUM: TUNED", "FLOW: READABLE"]
    status_text = status_options[feedback_id % len(status_options)]

    metadata_str = f"RITUAL ID: #{feedback_id}   |   TIMESTAMP: {created_at}   |   {status_text}"
    draw.text((120, 675), metadata_str, font=f_meta, fill=(179, 136, 255, 140))

    # 12. Динамический аватар проводника (в правом нижнем углу)
    skin_file = SKIN_VISUALS.get(active_skin, "o.png")
    skin_path = resolve_skin_path(skin_file)

    if skin_path and os.path.exists(skin_path):
        try:
            cond_img = Image.open(skin_path)
            # Обрезаем проводника в круг размера 110x110
            cond_avatar = crop_to_circle_with_border(cond_img, size=(110, 110), border_color=(255, 215, 0, 200), border_width=2, glow_color=(255, 215, 0, 80))
            # Помещаем в нижний правый угол
            base.paste(cond_avatar, (970, 525), cond_avatar)
        except Exception as e:
            logger.error(f"Error drawing conductor avatar: {e}")

    # Сохранение готовой картинки
    base = base.convert("RGB")
    base.save(output_path, "PNG")
    logger.success(f"Successfully generated crystal cosmic feedback card at {output_path}")

async def send_feedback_to_chat(vk_id: int, section: str, rating: int, comment_text: str, force: bool = False) -> tuple[bool, str]:
    """Сбор отзывов пачками по 4 штуки и публикация каруселью"""
    # Используем глобальную блокировку для предотвращения гонки при пакетной публикации
    if not await acquire_lock("batch_feedback_publish", ttl=60):
        return False, "Ресурс заблокирован. Попробуйте позже."

    try:
        # Получаем список неопубликованных отзывов
        unposted = await get_unposted_feedbacks(limit=4)

        if not unposted:
            logger.info("No unposted feedbacks found.")
            return False, "Нет неопубликованных отзывов для публикации."

        if not force and len(unposted) < 4:
            logger.info(f"Feedback queue: {len(unposted)}/4. Waiting for more.")
            return False, f"Очередь отзывов: {len(unposted)}/4. Ожидаем больше."

        logger.info(f"Starting publication (Force: {force}, Count: {len(unposted)})...")

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
            created_at = f.get("created_at")

            # Получаем имя и активного проводника пользователя
            user_data = await get_user(u_id)
            active_skin = "olesya"
            if user_data:
                full_name = f"{user_data.get('first_name', 'Адепт')} {user_data.get('last_name', '')}".strip() or "Адепт"
                active_skin = user_data.get("active_skin", "olesya")
            else:
                full_name = "Адепт"

            sec_ru = SECTION_NAMES.get(sec, sec.capitalize())

            # Скачиваем аватар пользователя из ВК асинхронно
            avatar_bytes = None
            try:
                vk_users = await bot.api.users.get(user_ids=[u_id], fields=["photo_200"])
                if vk_users and vk_users[0].photo_200:
                    avatar_url = vk_users[0].photo_200
                    async with aiohttp.ClientSession() as session:
                        async with session.get(avatar_url, timeout=5) as r:
                            if r.status == 200:
                                avatar_bytes = await r.read()
            except Exception as ex:
                logger.warning(f"Could not fetch or download user avatar for VK ID {u_id}: {ex}")

            temp_filename = f"feedback_batch_{f_id}_{random.randint(1000, 9999)}.png"
            temp_path = os.path.join("cards", temp_filename)

            # Рендерим карточку
            create_neon_feedback_card(
                user_name=full_name,
                section_name=sec_ru,
                rating=rat,
                comment=comm,
                output_path=temp_path,
                user_avatar_bytes=avatar_bytes,
                active_skin=active_skin,
                feedback_id=f_id,
                created_at=created_at
            )
            temp_files.append(temp_path)
            feedback_ids.append(f_id)

            # Загружаем в ВК (upload_wall_photo ожидает относительный путь к файлу внутри 'cards/', либо просто имя файла)
            att = await upload_wall_photo(bot.api, temp_filename)
            if att:
                attachments.append(att)

            await asyncio.sleep(0.5) # Небольшая пауза между загрузками

        if not attachments:
            logger.error("Failed to upload feedback batch cards to VK")
            return False, "Не удалось загрузить карточки отзывов в ВК."

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

        return True, f"Опубликована карусель из {len(attachments)} отзывов!"

    except Exception as e:
        logger.exception(f"Error in batch send_feedback_to_chat: {e}")
        return False, f"Ошибка при публикации: {e}"
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
