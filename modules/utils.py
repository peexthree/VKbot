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
from weasyprint import HTML

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


# ... (get_sections_keyboard, check_and_give_daily_bonus, generate_premium_pdf, MockMsg — оставил без изменений, они были в порядке)

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
