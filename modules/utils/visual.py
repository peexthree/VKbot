import os
import textwrap
from PIL import Image, ImageDraw, ImageFont

def generate_diagnosis_card(quote_text: str, output_path: str = "cards/temp_diagnosis.jpg"):
    """
    Генерирует стильную карточку с цитатой: темный градиент, шрифт Lora-Bold,
    текстовый вотермарк АНТИ-ТАР.
    """
    width, height = 1080, 1080

    # 1. Создание градиентного фона (от темно-серого к черному)
    # Верх: (40, 40, 40), Низ: (0, 0, 0)
    base = Image.new('RGB', (width, height), (0, 0, 0))
    top_color = (40, 40, 40)
    bottom_color = (0, 0, 0)

    draw = ImageDraw.Draw(base)
    for y in range(height):
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * (y / height))
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * (y / height))
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * (y / height))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # 2. Подготовка шрифтов
    font_path = "Lora-Bold.ttf"
    if not os.path.exists(font_path):
        # Фолбэк на системный, если файла нет (хотя он должен быть)
        font_path = "DejaVuSans-Bold.ttf"

    try:
        font_main = ImageFont.truetype(font_path, 60)
        font_logo = ImageFont.truetype(font_path, 40)
    except Exception:
        font_main = ImageFont.load_default()
        font_logo = ImageFont.load_default()

    # 3. Отрисовка цитаты (по центру с переносами)
    # Ограничиваем длину строки примерно 25-30 символами
    wrapped_text = textwrap.fill(quote_text, width=25)

    # Расчет координат для центрирования
    # getbbox возвращает (left, top, right, bottom)
    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font_main, align="center")
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (width - text_width) // 2
    y = (height - text_height) // 2 - 50 # Немного выше центра

    draw.multiline_text((x, y), wrapped_text, font=font_main, fill=(255, 255, 255), align="center", spacing=20)

    # 4. Вотермарк (АНТИ-ТАР)
    logo_text = "АНТИ-ТАР"
    logo_bbox = draw.textbbox((0, 0), logo_text, font=font_logo)
    logo_w = logo_bbox[2] - logo_bbox[0]

    lx = (width - logo_w) // 2
    ly = height - 100

    # Рисуем лого с небольшой прозрачностью (имитация через серый цвет)
    draw.text((lx, ly), logo_text, font=font_logo, fill=(150, 150, 150))

    # Сохранение
    base.save(output_path, "JPEG", quality=95)
    return output_path

if __name__ == "__main__":
    # Тестовый запуск
    generate_diagnosis_card("Таро — это костыль для тех, кто боится принимать решения самостоятельно.")
