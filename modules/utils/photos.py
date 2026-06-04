import os
import random
import asyncio
import aiohttp
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
            random_id=random.getrandbits(64)
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

    # Умный поиск файла (корень cards/ или подпапка uslugi/)
    if not os.path.exists(os.path.join("cards", filename)):
        if "uslugi/" in filename:
            alt_filename = filename.replace("uslugi/", "")
            if os.path.exists(os.path.join("cards", alt_filename)):
                filename = alt_filename
        else:
            alt_filename = f"uslugi/{filename}"
            if os.path.exists(os.path.join("cards", alt_filename)):
                filename = alt_filename

    cached = await get_cached_photo(filename)
    if cached:
        return cached
    lock_key = f"upload_lock:{filename}"
    locked = await acquire_lock(lock_key, ttl=30)
    if not locked:
        if peer_id:
            try:
                await bot_api.messages.send(peer_id=peer_id, message="Открываю гримуар...", random_id=random.getrandbits(64))
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

            # Retry mechanism for upload
            raw_photo_id = None
            last_err = None
            for attempt in range(3):
                try:
                    raw_photo_id = await uploader.upload(file_source=data, peer_id=0)
                    if raw_photo_id:
                        break
                except Exception as ex:
                    last_err = ex
                    logger.warning(f"Попытка {attempt+1} загрузки {filename} не удалась: {ex}")
                    await asyncio.sleep(1 * (attempt + 1))

            if not raw_photo_id:
                logger.error(f"Не удалось загрузить {filename} после 3 попыток. Последняя ошибка: {last_err}")
                return ""

            await _anchor_photo_and_cache(bot_api, filename, raw_photo_id)
            return raw_photo_id
    except Exception as e:
        logger.error(f"Критическая ошибка при обработке {filename}: {str(e)}")
        return ""
    finally:
        await release_lock(lock_key)


async def upload_wall_photo(bot_api, filename: str) -> str:
    """Специальная загрузка фото для постов на стену сообщества."""
    if not filename:
        return ""
    if filename in SKIN_ASSETS:
        filename = SKIN_ASSETS[filename]

    # Умный поиск файла
    if not os.path.exists(os.path.join("cards", filename)):
        if "uslugi/" in filename:
            alt_filename = filename.replace("uslugi/", "")
            if os.path.exists(os.path.join("cards", alt_filename)):
                filename = alt_filename
        else:
            alt_filename = f"uslugi/{filename}"
            if os.path.exists(os.path.join("cards", alt_filename)):
                filename = alt_filename

    # Кэш для фото на стене
    try:
        cached_id = await redis_client.get(f"wall_photo_v2:{filename}")
        if cached_id:
            return cached_id
    except Exception as e:
        logger.error(f"Ошибка чтения wall_photo из Redis: {str(e)}")

    lock_key = f"upload_wall_lock_v2:{filename}"
    locked = await acquire_lock(lock_key, ttl=30)
    if not locked:
        for _ in range(10):
            await asyncio.sleep(2)
            cached_id = await redis_client.get(f"wall_photo_v2:{filename}")
            if cached_id: return cached_id
        return ""

    try:
        # Пытаемся загрузить через photos.getMessagesUploadServer с получением Photo-объекта
        # чтобы иметь доступ к access_key.
        filepath = os.path.join("cards", filename)
        if not os.path.exists(filepath):
            logger.error(f"Файл не найден для wall_photo: {filepath}")
            return ""

        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()

            # Получаем сервер загрузки для сообщений
            server = await bot_api.photos.get_messages_upload_server()

            # Загружаем файл
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field('photo', data, filename='photo.jpg', content_type='image/jpeg')
                async with session.post(server.upload_url, data=form) as resp:
                    upload_data = await resp.json()

            # Сохраняем фото
            saved_photos = await bot_api.photos.save_messages_photo(
                photo=upload_data['photo'],
                server=upload_data['server'],
                hash=upload_data['hash']
            )

            if saved_photos:
                photo = saved_photos[0]
                logger.debug(f"Photo saved: owner_id={photo.owner_id}, id={photo.id}, has_access_key={bool(photo.access_key)}")

                # Формируем полный ID с access_key для надежности
                photo_attachment_id = f"photo{photo.owner_id}_{photo.id}"
                if photo.access_key:
                    photo_attachment_id += f"_{photo.access_key}"
                else:
                    logger.warning(f"Access key missing for photo {filename}! Post might be invisible on wall.")

                try:
                    await redis_client.set(f"wall_photo_v2:{filename}", photo_attachment_id)
                except Exception as e:
                    logger.error(f"Ошибка сохранения wall_photo в Redis: {str(e)}")
                return photo_attachment_id

            return ""
    except Exception as e:
        logger.error(f"Критическая ошибка при wall_photo {filename}: {str(e)}")
        # Фолбэк на старый метод если новый упал
        return await upload_local_photo(bot_api, filename)
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
