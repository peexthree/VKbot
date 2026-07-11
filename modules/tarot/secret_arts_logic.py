import hashlib
import os
import math
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from loguru import logger

# 1. Pillow-генератор сигилов
def generate_sigil_image(wish_text: str, output_path: str, background_path: str = "cards/uslugi/main_menu.jpeg"):
    """
    Генерирует уникальный сигил на основе хэша желания пользователя,
    рисует геометрическую композицию и накладывает текст желания шрифтом Lora.
    """
    try:
        # Пытаемся загрузить фоновое изображение
        if os.path.exists(background_path):
            base_img = Image.open(background_path).convert("RGBA")
        else:
            # Создаем красивый радиальный градиент по умолчанию (темно-космический)
            logger.warning(f"Background {background_path} not found. Creating a dark cosmic template.")
            base_img = Image.new("RGBA", (1080, 1080), (15, 10, 30, 255))
            draw_bg = ImageDraw.Draw(base_img)
            for r in range(540, 0, -4):
                alpha = int(255 * (r / 540))
                # Нежное свечение по центру
                draw_bg.ellipse((540 - r, 540 - r, 540 + r, 540 + r), fill=(25, 20, 45, 255 - alpha))

        # Масштабируем до 1080x1080 для стандартизации
        base_img = base_img.resize((1080, 1080), Image.Resampling.LANCZOS)
        width, height = base_img.size

        # Слой для неонового свечения
        glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_glow = ImageDraw.Draw(glow_layer)

        # Слой для четких линий поверх свечения
        sharp_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_sharp = ImageDraw.Draw(sharp_layer)

        # Вычисляем MD5 хэш желания пользователя
        h = hashlib.md5(wish_text.encode("utf-8")).hexdigest()
        nums = [int(h[i:i+2], 16) for i in range(0, len(h), 2)] # 16 чисел от 0 до 255

        cx, cy = width // 2, height // 2 - 50

        # Геометрические параметры на основе хэша
        r1 = 150 + (nums[0] % 80)  # Внутренний радиус
        r2 = 250 + (nums[1] % 100) # Средний радиус
        r3 = 380 + (nums[2] % 80)  # Внешний радиус

        # Отрисовка концентрических окружностей
        for draw in [draw_glow, draw_sharp]:
            width_val = 14 if draw == draw_glow else 3
            draw.ellipse((cx - r1, cy - r1, cx + r1, cy + r1), outline=(244, 212, 140, 255), width=width_val)
            draw.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), outline=(244, 212, 140, 255), width=width_val)
            draw.ellipse((cx - r3, cy - r3, cx + r3, cy + r3), outline=(244, 212, 140, 255), width=width_val)

        # Рисуем лучевые и ломаные линии (на основе тригонометрии от хэша)
        num_points = 6 + (nums[3] % 8) # От 6 до 13 вершин
        angles = [math.radians(360 * i / num_points + (nums[4] % 45)) for i in range(num_points)]

        points = []
        for i, angle in enumerate(angles):
            # Чередуем радиусы r2 и r3 для создания звезды/глифа
            r_curr = r2 if (i % 2 == 0) else r3
            px = cx + int(r_curr * math.cos(angle))
            py = cy + int(r_curr * math.sin(angle))
            points.append((px, py))

        # Соединяем вершины линиями
        for i in range(num_points):
            p_start = points[i]
            # Сложное перекрестное соединение (прыгаем через вершины на основе хэша)
            skip = 1 + (nums[5] % (num_points // 2 or 1))
            p_end = points[(i + skip) % num_points]

            for draw in [draw_glow, draw_sharp]:
                width_val = 12 if draw == draw_glow else 3
                draw.line([p_start, p_end], fill=(244, 212, 140, 255), width=width_val)

            # На концах лучей рисуем рунические засечки (маленькие кружки)
            for draw in [draw_glow, draw_sharp]:
                sub_r = 12 + (nums[i % len(nums)] % 10)
                width_val = 10 if draw == draw_glow else 2
                draw.ellipse((p_start[0] - sub_r, p_start[1] - sub_r, p_start[0] + sub_r, p_start[1] + sub_r), outline=(244, 212, 140, 255), width=width_val)

        # Размываем слой свечения для неонового эффекта
        glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(15))

        # Композиция слоев
        final_img = Image.alpha_composite(base_img, glow_blurred)
        final_img = Image.alpha_composite(final_img, sharp_layer)

        # Добавляем текст намерения снизу
        draw_text = ImageDraw.Draw(final_img)
        font_path = "Lora-Bold.ttf"
        font_regular_path = "Lora-Regular.ttf"

        if not os.path.exists(font_path): font_path = "arial.ttf"
        if not os.path.exists(font_regular_path): font_regular_path = "arial.ttf"

        font_title = ImageFont.truetype(font_path, 40)
        font_desc = ImageFont.truetype(font_regular_path, 32)

        # Текст заголовка
        title_text = "СА К Р А Л Ь Н Ы Й   С И Г И Л"
        w_title = draw_text.textlength(title_text, font=font_title)
        draw_text.text(((width - w_title) // 2, height - 160), title_text, fill=(244, 212, 140, 255), font=font_title)

        # Текст желания (обрезаем до 50 символов с многоточием)
        wish_clean = wish_text.strip()
        if len(wish_clean) > 50:
            wish_clean = wish_clean[:47] + "..."
        wish_clean = f"« {wish_clean.upper()} »"
        w_desc = draw_text.textlength(wish_clean, font=font_desc)
        draw_text.text(((width - w_desc) // 2, height - 100), wish_clean, fill=(255, 232, 163, 230), font=font_desc)

        # Сохраняем в формате JPEG
        final_img.convert("RGB").save(output_path, "JPEG", quality=95)
        logger.success(f"Сигил успешно сгенерирован и сохранен по пути: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка Pillow при генерации сигила: {e}")
        return False


# 2. Pillow-обработчик Окуломантии (глаз)
def process_oculomancy_eye(image_url_or_path: str, output_path: str, background_path: str = "cards/uslugi/main_menu.jpeg"):
    """
    Скачивает или открывает фото глаза, вырезает его по кругу,
    накладывает космическое небула-свечение и вписывает в изящное золотое кольцо с алхимическими символами.
    """
    try:
        if image_url_or_path.startswith("http"):
            import urllib.request
            with urllib.request.urlopen(image_url_or_path, timeout=15) as response:
                content = response.read()
                with open("temp_eye.jpg", "wb") as f:
                    f.write(content)
                eye_img = Image.open("temp_eye.jpg")
        else:
            eye_img = Image.open(image_url_or_path)

        eye_img = eye_img.convert("RGBA")

        # Обрезаем до квадрата по центру
        w, h = eye_img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        eye_img = eye_img.crop((left, top, left + side, top + side))
        eye_img = eye_img.resize((600, 600), Image.Resampling.LANCZOS)

        # Создаем маску-круг
        mask = Image.new("L", (600, 600), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((10, 10, 590, 590), fill=255)

        # Применяем маску
        round_eye = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
        round_eye.paste(eye_img, (0, 0), mask=mask)

        # Создаем фоновое изображение для глаза (крупнее на 200 пикселей, чтобы сделать роскошную рамку)
        final_w, final_h = 800, 800
        if os.path.exists(background_path):
            bg = Image.open(background_path).convert("RGBA").resize((final_w, final_h), Image.Resampling.LANCZOS)
        else:
            bg = Image.new("RGBA", (final_w, final_h), (15, 10, 30, 255))

        # Слои для свечения и тонкой отрисовки
        glow = Image.new("RGBA", (final_w, final_h), (0, 0, 0, 0))
        draw_glow = ImageDraw.Draw(glow)
        sharp = Image.new("RGBA", (final_w, final_h), (0, 0, 0, 0))
        draw_sharp = ImageDraw.Draw(sharp)

        cx, cy = final_w // 2, final_h // 2

        # Вставляем круглый глаз по центру
        bg.paste(round_eye, (cx - 300, cy - 300), mask=round_eye)

        # Рисуем золотую рамку-кольцо вокруг глаза
        r_ring = 300
        for draw in [draw_glow, draw_sharp]:
            width_val = 18 if draw == draw_glow else 4
            draw.ellipse((cx - r_ring, cy - r_ring, cx + r_ring, cy + r_ring), outline=(244, 212, 140, 255), width=width_val)

        # Рисуем тонкие эзотерические деления и рунические символы по ободу
        for i in range(12):
            angle = math.radians(i * (360 / 12))
            x1 = cx + int((r_ring - 15) * math.cos(angle))
            y1 = cy + int((r_ring - 15) * math.sin(angle))
            x2 = cx + int((r_ring + 15) * math.cos(angle))
            y2 = cy + int((r_ring + 15) * math.sin(angle))
            draw_sharp.line([x1, y1, x2, y2], fill=(244, 212, 140, 255), width=2)

        # Размываем свечение
        glow_blurred = glow.filter(ImageFilter.GaussianBlur(12))

        # Компонуем все элементы
        composite_bg = Image.alpha_composite(bg, glow_blurred)
        composite_bg = Image.alpha_composite(composite_bg, sharp)

        # Добавляем красивую надпись
        draw_text = ImageDraw.Draw(composite_bg)
        font_path = "Lora-Bold.ttf"
        if not os.path.exists(font_path): font_path = "arial.ttf"
        font = ImageFont.truetype(font_path, 32)

        title_text = "З Е Р К А Л О   Д У Ш И"
        w_title = draw_text.textlength(title_text, font=font)
        draw_text.text(((final_w - w_title) // 2, final_h - 60), title_text, fill=(244, 212, 140, 255), font=font)

        # Сохраняем в JPEG
        composite_bg.convert("RGB").save(output_path, "JPEG", quality=95)

        # Удаляем временный файл глаза, если он был скачан
        if os.path.exists("temp_eye.jpg"):
            os.remove("temp_eye.jpg")

        logger.success(f"Окуломантия-карточка глаза успешно создана: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка Pillow при обработке окуломантии: {e}")
        if os.path.exists("temp_eye.jpg"):
            os.remove("temp_eye.jpg")
        return False


# 3. Нумерологический Цифровой Алхимик
def calculate_alchemy_element(birth_date_str: str) -> dict:
    """
    Берет дату рождения DD.MM.YYYY, считает сумму цифр дня и месяца,
    приводит к числу от 1 до 3 (1 = Философская Ртуть, 2 = Сера, 3 = Соль).
    """
    try:
        # Извлекаем день и месяц
        parts = birth_date_str.split('.')
        day = int(parts[0])
        month = int(parts[1])

        # Суммируем все цифры дня и месяца
        total = sum(int(digit) for digit in f"{day}{month}")

        # Сворачиваем к числу от 1 до 3
        while total > 3:
            total = sum(int(digit) for digit in str(total))

        elements = {
            1: {"name": "ФИЛОСОФСКАЯ РТУТЬ", "latin": "Mercury", "symbol": "☿", "desc": "Стихия ума, трансформации, гибкости и чистой информации."},
            2: {"name": "СЕРА", "latin": "Sulfur", "symbol": "🜍", "desc": "Стихия внутренней искры, воли, страсти, действия и творческого огня."},
            3: {"name": "СОЛЬ", "latin": "Salt", "symbol": "🜔", "desc": "Стихия кристаллизации, структуры, заземления, накопления сил и опыта."}
        }
        return elements.get(total, elements[1])
    except Exception as e:
        logger.error(f"Ошибка при вычислении первоэлемента алхимика: {e}")
        return {"name": "ФИЛОСОФСКАЯ РТУТЬ", "latin": "Mercury", "symbol": "☿", "desc": "Стихия трансформации."}


# 4. Базы данных Древних Оракулов
EGYPTIAN_PAPYRUS = {
    "Анубис": "Ведущий дух-проводник сквозь тьму сомнений, взвешивает помыслы и устремления, дарует точность решений.",
    "Бастет": "Хранительница душевного тепла, интуиции и неявного очарования, раскрывает скрытые грани обаяния.",
    "Исида": "Священная матерь таинств, защитница и созидательница, наделяет космической силой возрождения.",
    "Осирис": "Владыка вечного перерождения, порядка и трансформации, помогает обрести баланс в кризисных ситуациях.",
    "Тот": "Ибис мудрости, покровитель древних знаний и письменности, раскрывает ментальные барьеры и новые учения.",
    "Ра": "Солнечное Око триумфа, символизирует ясность ума, победу над внутренними демонами и силу лидерства.",
    "Гор": "Священный Сокол справедливости, олицетворяет отвагу, защиту от коварства и триумф истинного зрения."
}

SHADOW_RUNES = {
    "Иса (Лед)": "Внутренняя заморозка, подавление эмоций, необходимость временного покоя перед великим пробуждением.",
    "Хагалаз (Разрушение)": "Внезапное разрушение ложных установок, экологичный взрыв иллюзий, очищение пространства.",
    "Наутиз (Нужда)": "Преодоление жестких ограничений и кармического долга, осознание внутренней силы через аскезу.",
    "Турисаз (Шип)": "Конфликтная сила, разрубающая узлы прошлого, жесткие личные границы и агрессивная защита.",
    "Перт (Тайна)": "Тайное знание, раскрытие теневого потенциала, возвращение подавленных воспоминаний и желаний."
}

def get_random_egyptian_oracle() -> list[dict]:
    """Случайно выбирает 3 сущности Египетского Оракула"""
    keys = random.sample(list(EGYPTIAN_PAPYRUS.keys()), 3)
    return [{"name": k, "desc": EGYPTIAN_PAPYRUS[k]} for k in keys]

def get_random_shadow_oracle() -> list[dict]:
    """Случайно выбирает 3 сущности Теневого Оракула"""
    keys = random.sample(list(SHADOW_RUNES.keys()), 3)
    return [{"name": k, "desc": SHADOW_RUNES[k]} for k in keys]
