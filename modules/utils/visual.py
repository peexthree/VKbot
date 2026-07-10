import os
import textwrap
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

def generate_card_history_image(card_id: int, card_name: str, output_path: str = "cards/temp_card_history.jpg"):
    """
    Генерирует стильную карточку для рубрики CARD_HISTORY:
    глубокий фиолетовый радиальный градиент, Аркан по центру,
    название Аркана сверху шрифтом Lora-Bold, логотип внизу.
    """
    width, height = 1080, 1080

    # 1. Создание радиального градиентного фона
    inner_color = (25, 12, 45)  # Глубокий холодный фиолетовый
    outer_color = (5, 2, 10)    # Почти черный

    mask = Image.new('L', (256, 256))
    for y in range(256):
        for x in range(256):
            dist = (((x - 128) ** 2 + (y - 128) ** 2) ** 0.5) / 128
            mask.putpixel((x, y), int(min(dist * 255, 255)))

    mask = mask.resize((width, height), Image.Resampling.LANCZOS)
    base = Image.new('RGB', (width, height), inner_color)
    outer_layer = Image.new('RGB', (width, height), outer_color)
    base = Image.composite(outer_layer, base, mask)

    draw = ImageDraw.Draw(base)

    # 2. Отрисовка названия Аркана сверху
    font_path = "Lora-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "DejaVuSans-Bold.ttf"

    try:
        font_title = ImageFont.truetype(font_path, 48)
    except Exception:
        font_title = ImageFont.load_default()

    title_text = f"АРКАН: {card_name.upper()}"
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    text_w = bbox[2] - bbox[0]

    # Рисуем заголовок сверху
    tx = (width - text_w) // 2
    ty = 60
    draw.text((tx, ty), title_text, font=font_title, fill=(255, 255, 255))

    # 3. Вставка изображения Аркана по центру
    card_filename = f"cards/{card_id}.jpeg"
    if os.path.exists(card_filename):
        try:
            card_img = Image.open(card_filename).convert("RGBA")
            # Пропорционально масштабируем до высоты 680px
            card_h = 680
            w_percent = (card_h / float(card_img.size[1]))
            card_w = int((float(card_img.size[0]) * float(w_percent)))
            card_img = card_img.resize((card_w, card_h), Image.Resampling.LANCZOS)

            cx = (width - card_w) // 2
            cy = 150 # Позиция по вертикали (под заголовком)

            base.paste(card_img, (cx, cy), card_img)
        except Exception as e:
            logger.error(f"Ошибка при обработке изображения Аркана {card_id}: {e}")

    # 4. Вставка логотипа внизу
    logo_path = "cards/uslugi/logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_w = 260
            w_percent = (logo_w / float(logo.size[0]))
            logo_h = int((float(logo.size[1]) * float(w_percent)))
            logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

            lx = (width - logo_w) // 2
            ly = height - logo_h - 40 # Снизу под картой

            base.paste(logo, (lx, ly), logo)
        except Exception as e:
            logger.error(f"Ошибка при вставке логотипа: {e}")

    base.save(output_path, "JPEG", quality=95)
    return output_path


def generate_diagnosis_card(quote_text: str, output_path: str = "cards/temp_diagnosis.jpg"):
    """
    Генерирует стильную карточку с цитатой: глубокий фиолетовый градиент,
    логотип Анти-Тар вместо текста, шрифт Lora-Bold.
    """
    width, height = 1080, 1080

    # 1. Создание радиального градиентного фона
    # Центр: глубокий фиолетовый, Края: почти черный
    inner_color = (25, 12, 45)  # Глубокий холодный фиолетовый
    outer_color = (5, 2, 10)    # Почти черный

    # Создаем маску для радиального градиента (быстрый способ через resize)
    mask = Image.new('L', (256, 256))
    for y in range(256):
        for x in range(256):
            # Расстояние от центра
            dist = (((x - 128) ** 2 + (y - 128) ** 2) ** 0.5) / 128
            mask.putpixel((x, y), int(min(dist * 255, 255)))

    mask = mask.resize((width, height), Image.Resampling.LANCZOS)

    # Композиция фона
    base = Image.new('RGB', (width, height), inner_color)
    outer_layer = Image.new('RGB', (width, height), outer_color)
    base = Image.composite(outer_layer, base, mask)

    draw = ImageDraw.Draw(base)

    # 2. Подготовка шрифтов
    font_path = "Lora-Bold.ttf"
    if not os.path.exists(font_path):
        font_path = "DejaVuSans-Bold.ttf"

    try:
        font_main = ImageFont.truetype(font_path, 60)
    except Exception:
        font_main = ImageFont.load_default()

    # 3. Отрисовка цитаты (по центру с переносами)
    wrapped_text = textwrap.fill(quote_text, width=28)

    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font_main, align="center")
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    tx = (width - text_width) // 2
    ty = (height - text_height) // 2 - 80 # Смещаем вверх для логотипа внизу

    draw.multiline_text((tx, ty), wrapped_text, font=font_main, fill=(255, 255, 255), align="center", spacing=25)

    # 4. Логотип вместо текстового вотермарка
    logo_path = "cards/uslugi/logo.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        # Пропорциональное изменение размера логотипа (ширина ~300px)
        logo_w = 320
        w_percent = (logo_w / float(logo.size[0]))
        logo_h = int((float(logo.size[1]) * float(w_percent)))
        logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

        lx = (width - logo_w) // 2
        ly = height - logo_h - 80 # Отступ снизу

        # Накладываем логотип (используя его альфа-канал)
        base.paste(logo, (lx, ly), logo)

    # Сохранение
    base.save(output_path, "JPEG", quality=95)
    return output_path

if __name__ == "__main__":
    # Тестовый запуск
    generate_diagnosis_card("Таро — это костыль для тех, кто боится принимать решения самостоятельно.")
