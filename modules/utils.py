import asyncio
import json
import os
import aiohttp
import aiofiles
from vkbottle import Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader

active_tasks = set()
cover_cache = {}

SKIN_ASSETS = {
    "Олеся Ивонченко": "o.png",
    "olesya": "o.png",
    "Серьезный Аскет": "as.jpeg",
    "asket": "as.jpeg",
    "Олег Шэпс": "ol.jpeg",
    "Влад Череватов": "2.jpeg",
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
    if not user:
        return keyboard.get_json()

    keyboard.add(Text("✦ Услуги"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("✦ Мой профиль"), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    keyboard.add(Text("✦ Главное меню"), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()

async def get_sections_keyboard(user_id: int, user: dict | None) -> str:
    purchased = user.get("purchased_sections", {}) if user else {}
    buttons = []

    # Секс
    if purchased.get("sex"):
        buttons.append([{"action": {"type": "text", "label": "👄 СЕКС"}, "color": "positive"}])

    # Деньги
    if purchased.get("money"):
        buttons.append([{"action": {"type": "text", "label": "💰 ДЕНЬГИ"}, "color": "positive"}])

    # Тень
    if purchased.get("shadow"):
        buttons.append([{"action": {"type": "text", "label": "🌘 ТЕНЬ"}, "color": "positive"}])

    # Финал
    if purchased.get("final"):
        buttons.append([{"action": {"type": "text", "label": "🏁 ФИНАЛ"}, "color": "positive"}])

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
        buttons.append([{"action": {"type": "text", "label": "СЕКС (РАЗОВАЯ)"}, "color": "secondary"}])

    if not purchased.get("money"):
        buttons.append([{"action": {"type": "text", "label": "ДЕНЬГИ (РАЗОВАЯ)"}, "color": "secondary"}])

    if not purchased.get("shadow"):
        buttons.append([{"action": {"type": "text", "label": "ТЕНЬ (РАЗОВАЯ)"}, "color": "secondary"}])

    if not purchased.get("final"):
        buttons.append([{"action": {"type": "text", "label": "ФИНАЛ (РАЗОВАЯ)"}, "color": "secondary"}])

    purchased_count = sum([bool(purchased.get("sex")), bool(purchased.get("money")), bool(purchased.get("shadow")), bool(purchased.get("final"))])
    if purchased_count < 2:
        buttons.append([{"action": {"type": "text", "label": "БАНДЛ"}, "color": "secondary"}])

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
    state_str = await get_user_state(vk_id)
    if not state_str:
        return None
    try:
        return json.loads(state_str)
    except Exception:
        return None

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import textwrap

def generate_pdf(text: str, filename: str):
    pdfmetrics.registerFont(TTFont('Roboto', 'Roboto.ttf'))
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    c.setFillColor(HexColor('#0F0F1A'))
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setFillColor(HexColor('#D4AF37'))
    c.setFont("Roboto", 24)
    c.drawCentredString(width / 2, height - 80, "ТВОЙ ПЕРСОНАЛЬНЫЙ АРХИВ")
    c.setFillColor(HexColor('#E53935'))
    c.setLineWidth(2)
    c.line(50, height - 100, width - 50, height - 100)
    c.setFillColor(HexColor('#FFFFFF'))
    c.setFont("Roboto", 12)

    y = height - 140
    margin = 50
    lines = text.split('\n')

    for line in lines:
        wrapped_lines = textwrap.wrap(line, width=70)
        for w_line in wrapped_lines:
            if y < 50:
                c.showPage()
                c.setFillColor(HexColor('#0F0F1A'))
                c.rect(0, 0, width, height, fill=1, stroke=0)
                c.setFillColor(HexColor('#FFFFFF'))
                c.setFont("Roboto", 12)
                y = height - 50
            c.drawString(margin, y, w_line)
            y -= 18
        y -= 10
    c.save()
