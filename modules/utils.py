import asyncio
import json
import os
import aiofiles
import datetime
from vkbottle import Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
from loguru import logger
from jinja2 import Environment, FileSystemLoader

cover_cache = {}

THEATRICAL_PHRASES = [
    "Считываю цифровой след...", "Открываю гримуар...", "Анализирую векторы вероятности...",
    "Настраиваюсь на ваши вибрации...", "Обращаюсь к древним арканам...", "Раскладываю карты судьбы...",
    "Запрашиваю ответ у мироздания...", "Синхронизирую потоки энергии...", "Читаю линии вероятности...",
    "Проникаю в тайны подсознания...", "Собираю осколки грядущего...", "Вслушиваюсь в шепот звезд...",
    "Приподнимаю завесу тайны...", "Сканирую энергетический фон...", "Анализирую кармические узлы..."
]

SKIN_ASSETS = {
    "Олеся Ивонченко": "o.png", "olesya": "o.png",
    "Серьезный Аскет": "as.jpeg", "asket": "as.jpeg",
    "Олег Шэпс": "ol.jpeg", "Влад Череватов": "2o.jpeg",
    "Виктория Райдес": "v.jpeg", "Александр Шеппс": "a.jpeg",
    "Баба Ванга": "ba.jpeg", "Григорий Распутин": "r.jpeg"
}

jinja_env = Environment(loader=FileSystemLoader('templates'))
pdf_semaphore = asyncio.Semaphore(1)

from cache import redis_client, acquire_lock, release_lock
ADMIN_ID = int(os.environ.get("ADMIN_ID", 27260796))

# (все функции get_cached_photo, flush_anchors, _anchor_photo_and_cache, clear_photo_cache, warmup_task, upload_local_photo, check_and_give_daily_bonus, get_dynamic_keyboard, get_sections_keyboard, get_fsm_step — точно как в твоём старом ZIP)

# === LAZY WEASYPRINT (решает OOM) ===
def generate_premium_pdf(user_name: str, birth_info: str, section_name: str, text_content: str, output_filename: str, card_id: str | None = None) -> bool:
    try:
        from weasyprint import HTML   # ← только здесь!

        template = jinja_env.get_template('report.html')
        formatted_text = text_content.replace('\n', '<br>')

        card_image_uri = ""
        if card_id:
            local_path = os.path.abspath(f"cards/{card_id}.jpeg")
            if os.path.exists(local_path):
                card_image_uri = f"file://{local_path}"

        html_out = template.render(
            user_name=user_name,
            birth_info=birth_info,
            section_name=section_name,
            text_content=formatted_text,
            card_image_path=card_image_uri
        )

        HTML(string=html_out).write_pdf(output_filename)
        logger.info(f"PDF создан: {output_filename}")
        return True
    except Exception as e:
        logger.error(f"Ошибка PDF: {str(e)}")
        return False
