import asyncio
import json
import os
import aiohttp
import aiofiles
from vkbottle import Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader

cover_cache = {}

SKIN_ASSETS = {
    "Олеся Ивонченко": "o.png",
    "olesya": "o.png",
    "Серьезный Аскет": "as.jpeg",
    "asket": "as.jpeg",
    "Олег Шэпс": "ol.jpeg",
    "Влад Череватов": "2o.jpeg",
    "Виктория Райдес": "v.jpeg",
    "Александр Шеппс": "a.jpeg",
    "Баба Ванга": "ba.jpeg",
    "Григорий Распутин": "r.jpeg"
}

async def upload_local_photo(bot_api, filename: str) -> str:
    """Загружает фото локально из папки cards/"""
    if filename in cover_cache:
        return cover_cache[filename]

    try:
        uploader = PhotoMessageUploader(bot_api)
        filepath = os.path.join("cards", filename)

        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()
            raw_photo_id = await uploader.upload(file_source=data, peer_id=0)
            cover_cache[filename] = raw_photo_id
            return raw_photo_id
    except Exception as e:
        print(f"Failed to upload local photo {filename}: {e}")
        return ""

def get_dynamic_keyboard(user: dict | None) -> str:
    keyboard = Keyboard(inline=False)
    keyboard.add(Text("✦ Услуги"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("🛰 ТАРИФЫ"), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text("✦ Мой профиль"), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text("✦ Путеводитель"), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text("✦ Главное меню"), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()

async def get_sections_keyboard(user_id: int, user: dict | None) -> str:
    purchased = user.get("purchased_sections", {}) if user else {}
    buttons = []

    # Секс
    if purchased.get("sex"):
        buttons.append([{"action": {"type": "text", "label": "👄 ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ"}, "color": "positive"}])

    # Деньги
    if purchased.get("money"):
        buttons.append([{"action": {"type": "text", "label": "💰 КОД ТВОЕГО БОГАТСТВА"}, "color": "positive"}])

    # Тень
    if purchased.get("shadow"):
        buttons.append([{"action": {"type": "text", "label": "🌘 ТВОИ СКРЫТЫЕ ГРАНИ"}, "color": "positive"}])

    # Финал
    if purchased.get("final"):
        buttons.append([{"action": {"type": "text", "label": "🏁 ТВОЙ ИСТИННЫЙ ПУТЬ"}, "color": "positive"}])

    if not buttons:
        buttons.append([{"action": {"type": "text", "label": "✦ УСЛУГИ 🛒"}, "color": "secondary"}])

    keyboard_obj = {
        "inline": True,
        "buttons": buttons
    }

    return json.dumps(keyboard_obj, ensure_ascii=False)

async def get_storefront_keyboard(purchased: dict) -> str | None:
    import json
    buttons = []

    if not purchased.get("sex"):
        buttons.append([{"action": {"type": "text", "label": "ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ"}, "color": "secondary"}])

    if not purchased.get("money"):
        buttons.append([{"action": {"type": "text", "label": "КОД ТВОЕГО БОГАТСТВА"}, "color": "secondary"}])

    if not purchased.get("shadow"):
        buttons.append([{"action": {"type": "text", "label": "ТВОИ СКРЫТЫЕ ГРАНИ"}, "color": "secondary"}])

    if not purchased.get("final"):
        buttons.append([{"action": {"type": "text", "label": "ТВОЙ ИСТИННЫЙ ПУТЬ"}, "color": "secondary"}])

    purchased_count = sum([bool(purchased.get("sex")), bool(purchased.get("money")), bool(purchased.get("shadow")), bool(purchased.get("final"))])
    if purchased_count < 2:
        buttons.append([{"action": {"type": "text", "label": "ЗОЛОТОЙ АРХИВ"}, "color": "secondary"}])

    # Oracle freemium skip button (always added as an option to purchase)
    buttons.append([{"action": {"type": "text", "label": "ВОПРОС СУДЬБЕ"}, "color": "secondary"}])

    if buttons:
        keyboard_obj = {
            "inline": True,
            "buttons": buttons
        }
        return json.dumps(keyboard_obj, ensure_ascii=False)
    return None

from modules.bot_init import bot

import json
from database import get_user_state

async def get_fsm_step(vk_id: int) -> dict | None:
    data = await get_user_state(vk_id)
    if data:
        try:
            return json.loads(data)
        except Exception:
            return None
    return None


import os
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

def generate_premium_pdf(user_name: str, birth_info: str, section_name: str, text_content: str, output_filename: str, card_id: str = None):
    try:
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('report.html')

        # Меняем переносы строк на HTML-теги
        formatted_text = text_content.replace('\n', '<br>')

        card_image_uri = ""
        if card_id:
            local_path = os.path.abspath(f"cards/{card_id}.jpeg")
            if os.path.exists(local_path):
                card_image_uri = f"file://{local_path}"
            else:
                card_image_uri = ""

        html_out = template.render(
            user_name=user_name,
            birth_info=birth_info,
            section_name=section_name,
            text_content=formatted_text,
            card_image_path=card_image_uri
        )

        HTML(string=html_out).write_pdf(output_filename)
        return True
    except Exception as e:
        print(f"Ошибка генерации PDF: {e}")
        return False
