import asyncio
import json
import os
import aiohttp
import aiofiles
import datetime
from vkbottle import Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
from loguru import logger
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

# Global imports to avoid local import overhead
from database import update_user, get_user_state

# Global cache for cover photo IDs
cover_cache = {}

THEATRICAL_PHRASES = [
    "Считываю цифровой след...",
    "Открываю гримуар...",
    "Анализирую векторы вероятности...",
    "Настраиваюсь на ваши вибрации...",
    "Обращаюсь к древним арканам...",
    "Раскладываю карты судьбы...",
    "Запрашиваю ответ у мироздания...",
    "Синхронизирую потоки энергии...",
    "Читаю линии вероятности...",
    "Проникаю в тайны подсознания...",
    "Собираю осколки грядущего...",
    "Вслушиваюсь в шепот звезд...",
    "Приподнимаю завесу тайны...",
    "Сканирую энергетический фон...",
    "Анализирую кармические узлы..."
]

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

# Pre-initialize Jinja2 Environment for faster PDF generation
templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
jinja_env = Environment(loader=FileSystemLoader('templates'))
pdf_semaphore = asyncio.Semaphore(1)

from cache import redis_client, acquire_lock, release_lock

ADMIN_ID = int(os.environ.get("ADMIN_ID", 27260796))

async def get_cached_photo(filename: str) -> str | None:
    # 1. Проверяем локальный кэш
    if filename in cover_cache:
        return cover_cache[filename]

    # 2. Проверяем Redis
    try:
        cached_id = await redis_client.get(f"photo:{filename}")
        if cached_id:
            cover_cache[filename] = cached_id
            return cached_id
    except Exception as e:
        logger.error(f"Ошибка чтения фото из Redis: {str(e)}")

    return None

async def _anchor_photo_and_cache(bot_api, filename: str, photo_id: str):
    # Якорим фото скрытым сообщением в Service Chat
    try:
        await bot_api.messages.send(
            peer_id=ADMIN_ID,
            message=f"System Anchor: {filename}",
            attachment=photo_id,
            random_id=0
        )
    except Exception as e:
        logger.error(f"Ошибка якорения фото {filename}: {str(e)}")

    # Сохраняем в локальный кэш и Redis
    cover_cache[filename] = photo_id
    try:
        await redis_client.set(f"photo:{filename}", photo_id)
    except Exception as e:
        logger.error(f"Ошибка сохранения фото в Redis: {str(e)}")

async def upload_local_photo(bot_api, filename: str, peer_id: int | None = None) -> str:
    """Загружает фото локально из папки cards/"""
    cached = await get_cached_photo(filename)
    if cached:
        return cached

    lock_key = f"upload_lock:{filename}"
    locked = await acquire_lock(lock_key, ttl=30)

    if not locked:
        # Если кто-то уже грузит эту карту
        if peer_id:
            try:
                await bot_api.messages.send(
                    peer_id=peer_id,
                    message="Открываю гримуар...",
                    random_id=0
                )
            except Exception:
                pass

        # Ждем пока загрузится (поллинг)
        for _ in range(15):
            await asyncio.sleep(2)
            cached = await get_cached_photo(filename)
            if cached:
                return cached
        return "" # Таймаут

    try:
        uploader = PhotoMessageUploader(bot_api)
        filepath = os.path.join("cards", filename)

        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()
            if len(data) < 100:
                logger.warning(f"Файл {filename} слишком мал ({len(data)} байт), пропуск загрузки.")
                return ""
            raw_photo_id = await uploader.upload(file_source=data, peer_id=0)
            await _anchor_photo_and_cache(bot_api, filename, raw_photo_id)
            return raw_photo_id
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return ""
    finally:
        await release_lock(lock_key)

async def check_and_give_daily_bonus(vk_id: int, user: dict | None, peer_id: int):
    """Проверяет и выдает ежедневный бонус (100 Энергии звезд) при отрисовке меню"""
    if not user:
        return
        
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
            logger.error(f"Ошибка: {str(e)}")


async def start_dynamic_typing(bot_api, peer_id: int, message_id: int | None, conversation_message_id: int | None = None):
    import random
    import asyncio
    from loguru import logger

    async def loop():
        try:
            while True:
                await asyncio.sleep(10)
                new_text = random.choice(THEATRICAL_PHRASES)
                try:
                    if conversation_message_id:
                        await bot_api.messages.edit(
                            peer_id=peer_id,
                            message=new_text,
                            conversation_message_id=conversation_message_id
                        )
                    elif message_id:
                        await bot_api.messages.edit(
                            peer_id=peer_id,
                            message=new_text,
                            message_id=message_id
                        )
                except Exception as e:
                    # Ignore API errors like message too old or identical text
                    pass

                try:
                    await bot_api.messages.set_activity(peer_id=peer_id, type="typing")
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    return asyncio.create_task(loop())

def get_dynamic_keyboard(user: dict | None = None) -> str:
    """Генерирует главную (нижнюю) клавиатуру с Картой дня и Путеводителем"""
    keyboard = Keyboard(inline=False)
    
    keyboard.add(Text("🃏 КАРТА ДНЯ"), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("🔮 ГЛУБОКИЕ РАЗБОРЫ"), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    
    keyboard.add(Text("💳 МОЙ ПРОФИЛЬ"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("📖 ПУТЕВОДИТЕЛЬ"), color=KeyboardButtonColor.SECONDARY)
    
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
    # Эта функция больше не используется для основной витрины
    return None

async def get_fsm_step(vk_id: int) -> dict | None:
    data = await get_user_state(vk_id)
    if data:
        try:
            return json.loads(data)
        except Exception:
            return None
    return None

def generate_premium_pdf(user_name: str, birth_info: str, section_name: str, text_content: str, output_filename: str, card_id: str = None):
    try:
        template = jinja_env.get_template('report.html')

        # Меняем переносы строк на HTML-теги
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
        return True
    except Exception as e:
        logger.error(f"Ошибка PDF: {str(e)}")
        return False
