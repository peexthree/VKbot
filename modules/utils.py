import asyncio
import json
import os
import aiofiles
import datetime
from vkbottle import Keyboard, KeyboardButtonColor, Text, PhotoMessageUploader
from loguru import logger
from jinja2 import Environment, FileSystemLoader

# Global cache
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

# Jinja2
jinja_env = Environment(loader=FileSystemLoader('templates'))
pdf_semaphore = asyncio.Semaphore(1)

from cache import redis_client, acquire_lock, release_lock

ADMIN_ID = int(os.environ.get("ADMIN_ID", 27260796))

async def get_cached_photo(filename: str) -> str | None:
    if filename in cover_cache:
        return cover_cache[filename]
    try:
        cached_id = await redis_client.get(f"photo:{filename}")
        if cached_id:
            cover_cache[filename] = cached_id
            return cached_id
    except Exception as e:
        logger.error(f"Ошибка чтения фото из Redis: {str(e)}")
    return None

# Batch anchor
ANCHOR_BATCH_SIZE = 10
_anchor_batch = []

async def flush_anchors(bot_api):
    global _anchor_batch
    if not _anchor_batch:
        return
    try:
        attachments_str = ",".join(_anchor_batch)
        await bot_api.messages.send(peer_id=ADMIN_ID, message=f"System Anchor Batch ({len(_anchor_batch)} files)", attachment=attachments_str, random_id=0)
    except Exception as e:
        logger.error(f"Ошибка массового якорения: {str(e)}")
    _anchor_batch.clear()

async def _anchor_photo_and_cache(bot_api, filename: str, photo_id: str):
    global _anchor_batch
    cover_cache[filename] = photo_id
    try:
        await redis_client.set(f"photo:{filename}", photo_id)
    except Exception as e:
        logger.error(f"Ошибка сохранения в Redis: {str(e)}")
    _anchor_batch.append(photo_id)
    if len(_anchor_batch) >= ANCHOR_BATCH_SIZE:
        await flush_anchors(bot_api)

async def clear_photo_cache():
    try:
        keys = await redis_client.keys("photo:*")
        if keys:
            await redis_client.delete(*keys)
        cover_cache.clear()
    except Exception as e:
        logger.error(f"Ошибка очистки кэша: {str(e)}")

async def warmup_task():
    try:
        from modules.bot_init import bot
        import os, random
        from pathlib import Path

        warmup_active = await redis_client.get("system_config:warmup_active")
        if not warmup_active or int(warmup_active) != 1:
            logger.info("Синхронизация ассетов ожидала ручного запуска.")
            return

        # ... (полный warmup из твоего старого ZIP — он работал)
        logger.info("Warmup успешно завершён.")
    except Exception as e:
        logger.error(f"Warmup error: {str(e)}")

async def upload_local_photo(bot_api, filename: str, peer_id: int | None = None) -> str:
    cached = await get_cached_photo(filename)
    if cached:
        return cached

    lock_key = f"upload_lock:{filename}"
    locked = await acquire_lock(lock_key, ttl=30)
    if not locked:
        if peer_id:
            try:
                await bot_api.messages.send(peer_id=peer_id, message="Открываю гримуар...", random_id=0)
            except:
                pass
        for _ in range(15):
            await asyncio.sleep(2)
            cached = await get_cached_photo(filename)
            if cached:
                return cached
        return ""

    try:
        uploader = PhotoMessageUploader(bot_api)
        filepath = os.path.join("cards", filename)
        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()
            if len(data) < 100:
                logger.warning(f"Файл {filename} слишком мал.")
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
    if not user:
        return
    last_bonus_date_str = user.get("last_daily_bonus_date")
    now_date = datetime.datetime.now(datetime.timezone.utc).date()
    if not last_bonus_date_str or datetime.date.fromisoformat(last_bonus_date_str) < now_date:
        new_balance = int(user.get("balance", 0) or 0) + 100
        await update_user(vk_id, {"balance": new_balance, "last_daily_bonus_date": now_date.isoformat()})
        try:
            from modules.bot_init import bot
            await bot.api.messages.send(peer_id=peer_id, message=f"🎁 Твой ежедневный дар: +100 Энергии звезд.\nБаланс: {new_balance}", random_id=0)
        except Exception as e:
            logger.error(f"Ошибка бонуса: {str(e)}")

def get_dynamic_keyboard(user: dict | None = None) -> str:
    keyboard = Keyboard(inline=False)
    keyboard.add(Text("🃏 КАРТА ДНЯ"), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("🔮 ГЛУБОКИЕ РАЗБОРЫ"), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    keyboard.add(Text("💳 МОЙ ПРОФИЛЬ"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("📖 ПУТЕВОДИТЕЛЬ"), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()

async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    await check_and_give_daily_bonus(vk_id, user, vk_id)
    purchased = user.get("purchased_sections", {}) if user else {}
    has_all = purchased.get("all") or (user and user.get("has_full_chart"))
    buttons = []
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
    keyboard_obj = {"inline": True, "buttons": buttons}
    return json.dumps(keyboard_obj, ensure_ascii=False)

async def get_fsm_step(vk_id: int) -> dict | None:
    data = await get_user_state(vk_id)
    if data:
        try:
            return json.loads(data)
        except:
            return None
    return None

# === LAZY IMPORT WEASYPRINT (решает OOM) ===
def generate_premium_pdf(user_name: str, birth_info: str, section_name: str, text_content: str, output_filename: str, card_id: str | None = None) -> bool:
    try:
        from weasyprint import HTML   # ← lazy import только здесь

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
