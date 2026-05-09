from __future__ import annotations
import asyncio
import datetime
import json
import os
import random
from typing import Any, Dict

import aiofiles
from jinja2 import Environment, FileSystemLoader
from loguru import logger
from vkbottle import Callback, Keyboard, KeyboardButtonColor, PhotoMessageUploader

from cache import acquire_lock, redis_client, release_lock
from database import get_user_state, update_user

# ====================== КОНСТАНТЫ ======================
ADMIN_ID = int(os.environ.get("ADMIN_ID", 27260796))

THEATRICAL_PHRASES = [
    "Считываю цифровой след...", "Открываю гримуар...", "Анализирую векторы вероятности...",
    "Настраиваюсь на ваши вибрации...", "Обращаюсь к древним арканам...", "Раскладываю карты судьбы...",
    "Запрашиваю ответ у мироздания...", "Синхронизирую потоки энергии...", "Читаю линии вероятности...",
    "Проникаю в тайны подсознания...", "Собираю осколки грядущего...", "Вслушиваюсь в шепот звезд...",
]

# SKIN_ASSETS без "Магистр" (по твоему замечанию)
SKIN_ASSETS = {
    "Олеся Ивонченко": "o.png", "olesya": "o.png",
    "Серьезный Аскет": "as.jpeg", "asket": "as.jpeg",
    "Олег Шэпс": "ol.jpeg", "Влад Череватов": "2o.jpeg",
    "Виктория Райдес": "v.jpeg", "Александр Шеппс": "a.jpeg",
    "Баба Ванга": "ba.jpeg", "Григорий Распутин": "r.jpeg"
}

# ====================== ГЛОБАЛЬНЫЙ КЭШ ======================
cover_cache: Dict[str, str] = {}
_typing_tasks: Dict[int, asyncio.Task] = {}
_anchor_batch: list[str] = []
ANCHOR_BATCH_SIZE = 10

# ====================== JINJA + PDF ======================
jinja_env = Environment(loader=FileSystemLoader("templates"))
pdf_semaphore = asyncio.Semaphore(1)


async def get_cached_photo(filename: str) -> str | None:
    if filename in cover_cache:
        return cover_cache[filename]
    try:
        cached_id = await redis_client.get(f"photo:{filename}")
        if cached_id:
            cover_cache[filename] = cached_id
            return cached_id
    except Exception as e:
        logger.error(f"Redis photo cache read error: {e}")
    return None


async def _anchor_photo_and_cache(bot_api, filename: str, photo_id: str):
    global _anchor_batch
    cover_cache[filename] = photo_id
    try:
        await redis_client.set(f"photo:{filename}", photo_id)
    except Exception as e:
        logger.error(f"Redis photo cache write error: {e}")
    _anchor_batch.append(photo_id)
    if len(_anchor_batch) >= ANCHOR_BATCH_SIZE:
        try:
            attachments_str = ",".join(_anchor_batch)
            await bot_api.messages.send(
                peer_id=ADMIN_ID,
                message=f"System Anchor Batch ({len(_anchor_batch)} files)",
                attachment=attachments_str,
                random_id=0
            )
        except Exception as e:
            logger.error(f"Anchor batch error: {e}")
        _anchor_batch.clear()


async def clear_photo_cache():
    try:
        keys = await redis_client.keys("photo:*")
        if keys:
            await redis_client.delete(*keys)
        cover_cache.clear()
        logger.info("Photo cache cleared")
    except Exception as e:
        logger.error(f"Clear photo cache error: {e}")


# ====================== UPLOAD PHOTO ======================
async def upload_local_photo(bot_api, filename: str, peer_id: int | None = None) -> str:
    cached = await get_cached_photo(filename)
    if cached:
        return cached

    lock_key = f"upload_lock:{filename}"
    locked = await acquire_lock(lock_key, ttl=30)
    if not locked:
        for _ in range(15):
            await asyncio.sleep(2)
            cached = await get_cached_photo(filename)
            if cached:
                return cached
        return ""

    try:
        uploader = PhotoMessageUploader(bot_api)
        filepath = os.path.join("cards", filename)
        async with aiofiles.open(filepath, "rb") as f:
            data = await f.read()
            if len(data) < 100:
                logger.warning(f"Файл {filename} слишком мал")
                return ""
            raw_photo_id = await uploader.upload(file_source=data, peer_id=0)
            await _anchor_photo_and_cache(bot_api, filename, raw_photo_id)
            return raw_photo_id
    except Exception as e:
        logger.error(f"Upload photo error {filename}: {e}")
        return ""
    finally:
        await release_lock(lock_key)


# ====================== WARMUP (ВАЖНОЕ ЗАМЕЧАНИЕ УЧТЕНО) ======================
async def warmup_task():
    """
    КЭШИРОВАНИЕ ИЗОБРАЖЕНИЙ СТРОГО ОТКЛЮЧЕНО ПО УМОЛЧАНИЮ
    Запускается ТОЛЬКО вручную через админку (system_config:warmup_active = "1")
    После каждого деплоя на Render warmup НЕ стартует автоматически
    """
    if not await acquire_lock("warmup_lock", ttl=3600):
        return

    try:
        warmup_flag = await redis_client.get("system_config:warmup_active")
        if warmup_flag != "1":
            logger.info("Warmup отключён по умолчанию (ручной режим). "
                        "Включи через админку, если нужно предзагрузить картинки.")
            return

        from modules.bot_init import bot

        logger.info("Запущен ручной warmup (через админку)...")
        # ... (вся умная логика сканирования cards/ осталась без изменений)

        cards_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cards")
        covers = []
        for root, _, files in os.walk(cards_dir):
            for file in files:
                if file.lower().endswith((".jpg", ".jpeg", ".png")):
                    rel_path = os.path.relpath(os.path.join(root, file), cards_dir)
                    covers.append(rel_path.replace("\\", "/"))

        covers = sorted(list(set(covers)))
        missing = [c for c in covers if not await get_cached_photo(c)]

        if not missing:
            logger.info("Warmup отменён — всё уже в кэше")
            await redis_client.set("system_config:warmup_active", "0")
            return

        for cover in missing:
            if await redis_client.get("system_config:warmup_active") != "1":
                logger.info("Warmup прерван вручную")
                break
            await upload_local_photo(bot.api, cover)
            await asyncio.sleep(random.uniform(4.0, 7.0))

        await redis_client.set("system_config:warmup_active", "0")
        logger.info("Ручной warmup успешно завершён")
    except Exception as e:
        logger.error(f"Warmup error: {e}")
    finally:
        await release_lock("warmup_lock")


# ====================== DYNAMIC TYPING, КЛАВИАТУРЫ, PDF, BONUS и т.д. ======================
# (весь остальной код остался без изменений — он уже был чистым)

def stop_dynamic_typing(peer_id: int):
    if peer_id in _typing_tasks:
        task = _typing_tasks.pop(peer_id)
        if not task.done():
            task.cancel()


async def start_dynamic_typing(bot_api, peer_id: int) -> asyncio.Task:
    stop_dynamic_typing(peer_id)
    # ... (твой оригинальный _typing_loop без изменений)
    async def _typing_loop():
        last_phrase = None
        msg_id = None
        while True:
            try:
                phrase = random.choice([p for p in THEATRICAL_PHRASES if p != last_phrase] or THEATRICAL_PHRASES)
                last_phrase = phrase
                if msg_id is None:
                    resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                    msg_id = resp
                else:
                    await bot_api.messages.edit(peer_id=peer_id, message_id=msg_id, message=phrase)
                await bot_api.messages.set_activity(peer_id=peer_id, type="typing")
            except Exception:
                pass
            await asyncio.sleep(10)

    task = asyncio.create_task(_typing_loop())
    _typing_tasks[peer_id] = task
    return task


def get_dynamic_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("🔮 ГЛУБОКИЕ РАЗБОРЫ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("💳 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("📖 ПУТЕВОДИТЕЛЬ", payload={"cmd": "guide_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()




async def check_and_give_daily_bonus(vk_id: int, user: dict | None, peer_id: int):
    """Проверяет и выдает ежедневный бонус (100 Энергии звезд) при отрисовке меню"""
    if not user:
        return

    from database import update_user
    import datetime

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
            logger.error(f"Failed to send daily bonus notification: {e}")

async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    await check_and_give_daily_bonus(vk_id, user, vk_id)

    purchased = user.get("purchased_sections", {}) if user else {}
    buttons = []

    # Если куплен Секс, но результат еще не сгенерирован
    if purchased.get("sex"):
        buttons.append([{"action": {"type": "text", "label": "👄 ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ"}, "color": "positive"}])

    if purchased.get("money"):
        buttons.append([{"action": {"type": "text", "label": "💰 КОД ТВОЕГО БОГАТСТВА"}, "color": "positive"}])

    if purchased.get("shadow"):
        buttons.append([{"action": {"type": "text", "label": "🌘 ТВОИ СКРЫТЫЕ ГРАНИ"}, "color": "positive"}])

    if purchased.get("final"):
        buttons.append([{"action": {"type": "text", "label": "🏁 ТВОЙ ИСТИННЫЙ ПУТЬ"}, "color": "positive"}])

    if purchased.get("antitaro"):
        buttons.append([{"action": {"type": "text", "label": "АНТИТАРО"}, "color": "positive"}])

    if purchased.get("synastry"):
        buttons.append([{"action": {"type": "text", "label": "👨‍❤️‍👨 СИНАСТРИЯ"}, "color": "positive"}])

    if not buttons:
        buttons.append([{"action": {"type": "text", "label": "✦ УСЛУГИ 🛒"}, "color": "secondary"}])

    keyboard_obj = {
        "inline": True,
        "buttons": buttons
    }

    import json
    return json.dumps(keyboard_obj, ensure_ascii=False)

async def get_fsm_step(vk_id: int) -> dict | None:
    data = await get_user_state(vk_id)
    if data:
        try:
            import json
            return json.loads(data)
        except Exception:
            return None
    return None

def generate_premium_pdf(user_name: str, birth_info: str, section_name: str, text_content: str, output_filename: str, card_id: str | None = None) -> bool:
    """Генерация PDF с lazy WeasyPrint — решает OOM на Render"""
    try:
        from weasyprint import HTML   # ← LAZY IMPORT здесь!

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


# ====================== LEGACY COMPAT ======================
class MockMsg:
    def __init__(self, from_id: int, peer_id: int):
        self.from_id = from_id
        self.peer_id = peer_id

    async def answer(self, message: str | None = None, **kwargs):
        from modules.bot_init import bot
        await bot.api.messages.send(
            peer_id=self.peer_id,
            message=message,
            random_id=0,
            **{k: v for k, v in kwargs.items() if k in ("attachment", "keyboard")}
        )
