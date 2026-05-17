import os
import random
import asyncio
from pathlib import Path
import aiofiles
from loguru import logger
from vkbottle import PhotoMessageUploader
from cache import acquire_lock, redis_client, release_lock
from modules.utils.consts import (
    SKIN_ASSETS, cover_cache, _anchor_batch, ANCHOR_BATCH_SIZE, ADMIN_ID
)

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

async def flush_anchors(bot_api):
    global _anchor_batch
    if not _anchor_batch:
        return
    try:
        attachments_str = ",".join(_anchor_batch)
        await bot_api.messages.send(
            peer_id=ADMIN_ID,
            message=f"System Anchor Batch ({len(_anchor_batch)} files)",
            attachment=attachments_str,
            random_id=0
        )
    except Exception as e:
        logger.error(f"Ошибка массового якорения фото: {str(e)}")
    _anchor_batch.clear()

async def _anchor_photo_and_cache(bot_api, filename: str, photo_id: str):
    global _anchor_batch
    cover_cache[filename] = photo_id
    try:
        await redis_client.set(f"photo:{filename}", photo_id)
    except Exception as e:
        logger.error(f"Ошибка сохранения фото в Redis: {str(e)}")
    _anchor_batch.append(photo_id)
    if len(_anchor_batch) >= ANCHOR_BATCH_SIZE:
        await flush_anchors(bot_api)

async def upload_local_photo(bot_api, filename: str, peer_id: int | None = None) -> str:
    if not filename:
        return ""
    if filename in SKIN_ASSETS:
        filename = SKIN_ASSETS[filename]
    cached = await get_cached_photo(filename)
    if cached:
        return cached
    lock_key = f"upload_lock:{filename}"
    locked = await acquire_lock(lock_key, ttl=30)
    if not locked:
        if peer_id:
            try:
                from modules.utils.ui import ghost_edit
                await ghost_edit(bot_api, peer_id, "Открываю гримуар...")
            except Exception: pass
        for _ in range(15):
            await asyncio.sleep(2)
            cached = await get_cached_photo(filename)
            if cached: return cached
        return ""
    try:
        uploader = PhotoMessageUploader(bot_api)
        filepath = os.path.join("cards", filename)
        if not os.path.exists(filepath):
            logger.error(f"Файл не найден: {filepath}")
            return ""
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

async def warmup_task():
    if not await acquire_lock("warmup_lock", ttl=3600):
        logger.info("Warmup task already running (lock active).")
        return
    try:
        from modules.bot_init import bot
        warmup_active = await redis_client.get("system_config:warmup_active")
        if not warmup_active or int(warmup_active) != 1:
            logger.info("Синхронизация ассетов ожидала ручного запуска. Режим тишины активен.")
            return
        covers = []
        cards_dir = Path("cards")
        if cards_dir.exists():
            for root, _, files in os.walk(cards_dir):
                for file in files:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                        full_path = Path(root) / file
                        rel_path = full_path.relative_to(cards_dir)
                        covers.append(str(rel_path).replace("\\", "/"))
        for i in range(78):
            name = f"{i}.jpeg"
            if name not in covers and (cards_dir / name).exists():
                covers.append(name)
        covers = sorted(list(set(covers)))
        missing_covers = []
        for cover in covers:
            if not await get_cached_photo(cover):
                missing_covers.append(cover)
        if not missing_covers:
            logger.info("Предзагрузка (Warmup) отменена: все картинки уже в кэше.")
            await flush_anchors(bot.api)
            await redis_client.set("system_config:warmup_active", "0")
            return
        logger.info(f"Запуск умной загрузки (Warmup) для {len(missing_covers)} картинок...")
        for cover in missing_covers:
            is_active = await redis_client.get("system_config:warmup_active")
            if not is_active or int(is_active) != 1:
                logger.info("Синхронизация ассетов прервана вручную.")
                await flush_anchors(bot.api)
                return
            await upload_local_photo(bot.api, cover)
            await asyncio.sleep(random.uniform(4.0, 7.0))
        await flush_anchors(bot.api)
        await redis_client.set("system_config:warmup_active", "0")
        logger.info("Предзагрузка (Warmup) картинок успешно завершена.")
    except Exception as e:
        logger.error(f"Ошибка при предзагрузке (Warmup) картинок: {str(e)}")
    finally:
        await release_lock("warmup_lock")

async def clear_photo_cache():
    try:
        keys = await redis_client.keys("photo:*")
        if keys:
            await redis_client.delete(*keys)
        cover_cache.clear()
    except Exception as e:
        logger.error(f"Ошибка при очистке кэша фото: {str(e)}")
