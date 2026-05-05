import asyncio
import json
import os
import aiohttp
import aiofiles
import datetime
from vkbottle import Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
from loguru import logger

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
        logger.exception(f"Failed to upload local photo {filename}: {e}")
        return ""

async def check_and_give_daily_bonus(vk_id: int, user: dict | None, peer_id: int):
    """Проверяет и выдает ежедневный бонус (100 Энергии звезд) при отрисовке меню"""
    if not user:
        return
        
    from database import update_user
    
    last_bonus_date_str = user.get("last_daily_bonus_date")
    now_date = datetime.datetime.now(datetime.timezone.utc).date()
    
    should_give = False
    
    if not last_bonus_date_str:
        should_give = True
    else:
        try:
            last_bonus_date = datetime.date.fromisoformat(last_bonus_date_str)
            if now_date > last_bonus_date:
                should_give = True
        except ValueError:
            should_give = True
            
    if should_give:
        current_balance = int(user.get("balance", 0) or 0)
        new_balance = current_balance + 100
        await update_user(vk_id, {
            "balance": new_balance, 
            "last_daily_bonus_date": now_date.isoformat()
        })
        try:
            from modules.bot_init import bot
            await bot.api.messages.send(
                peer_id=peer_id, 
                message=f"🎁 Твой ежедневный дар: +100 Энергии звезд.\nВозвращайся завтра за новой порцией. Твой баланс: {new_balance}.", 
                random_id=0
            )
        except Exception as e:
            logger.exception(f"Failed to send daily bonus notification: {e}")


def get_dynamic_keyboard(user: dict | None = None) -> str:
    """Генерирует главную (нижнюю) клавиатуру с Картой дня и Путеводителем"""
    keyboard = Keyboard(inline=False)
    
    keyboard.add(Text("✦ Услуги"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("🛰 ТАРИФЫ"), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    
    keyboard.add(Text("🃏 Карта дня"), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("✦ Мой профиль"), color=KeyboardButtonColor.PRIMARY)
    keyboard.row()
    
    keyboard.add(Text("📖 Путеводитель"), color=KeyboardButtonColor.SECONDARY)
    
    return keyboard.get_json()

async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    """Генерирует инлайн клавиатуру для открытых (купленных) разделов"""
    # Заодно при отрисовке инлайн-кнопок меню выдадим бонус, если наступил новый день
    await check_and_give_daily_bonus(vk_id, user, vk_id)
    
    purchased = user.get("purchased_sections", {}) if user else {}
    has_all = purchased.get("all") or (user and user.get("has_full_chart"))
    buttons = []

    # Если куплен Секс, но результат еще не сгенерирован
    if purchased.get("sex") or has_all:
        buttons.append([{"action": {"type": "callback", "payload": json.dumps({"cmd": "use_section", "key": "sex"}), "label": "👄 ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ"}, "color": "positive"}])

    if purchased.get("money") or has_all:
        buttons.append([{"action": {"type": "callback", "payload": json.dumps({"cmd": "use_section", "key": "money"}), "label": "💰 КОД ТВОЕГО БОГАТСТВА"}, "color": "positive"}])

    if purchased.get("shadow") or has_all:
        buttons.append([{"action": {"type": "callback", "payload": json.dumps({"cmd": "use_section", "key": "shadow"}), "label": "🌘 ТВОИ СКРЫТЫЕ ГРАНИ"}, "color": "positive"}])

    if purchased.get("final") or has_all:
        buttons.append([{"action": {"type": "callback", "payload": json.dumps({"cmd": "use_section", "key": "final"}), "label": "🏁 ТВОЙ ИСТИННЫЙ ПУТЬ"}, "color": "positive"}])
        
    if purchased.get("antitaro"):
        buttons.append([{"action": {"type": "callback", "payload": json.dumps({"cmd": "use_section", "key": "antitaro"}), "label": "АНТИТАРО"}, "color": "positive"}])
        
    if purchased.get("synastry"):
        buttons.append([{"action": {"type": "callback", "payload": json.dumps({"cmd": "use_section", "key": "synastry"}), "label": "👨‍❤️‍👨 СИНАСТРИЯ"}, "color": "positive"}])

    if not buttons:
        buttons.append([{"action": {"type": "callback", "payload": json.dumps({"cmd": "service_page", "idx": 0}), "label": "✦ УСЛУГИ 🛒"}, "color": "secondary"}])

    keyboard_obj = {
        "inline": True,
        "buttons": buttons
    }

    return json.dumps(keyboard_obj, ensure_ascii=False)

async def get_storefront_keyboard(purchased: dict) -> str | None:
    # Эта функция больше не используется для основной витрины (мы используем карусель из services.py)
    # Оставляем пустую реализацию для совместимости со старыми модулями
    return None

from modules.bot_init import bot
from database import get_user_state

async def get_fsm_step(vk_id: int) -> dict | None:
    data = await get_user_state(vk_id)
    if data:
        try:
            return json.loads(data)
        except Exception as e:
            return None
    return None


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
        logger.exception(f"Ошибка генерации PDF: {e}")
        return False
