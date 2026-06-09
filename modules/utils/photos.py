import os
import random
import asyncio
import aiohttp
from pathlib import Path
import aiofiles
from loguru import logger
from vkbottle import API
from cache import acquire_lock, redis_client, release_lock
from modules.utils.consts import (
    SKIN_ASSETS, cover_cache, _anchor_batch, ANCHOR_BATCH_SIZE, ADMIN_ID, GROUP_ID
)

_user_api: API | None = None

def get_user_api() -> API | None:
    """Инициализирует и возвращает API клиента пользователя (ленивая инициализация)."""
    global _user_api
    if _user_api is not None:
        return _user_api

    token = os.environ.get("USER_ACCESS_TOKEN")
    if not token:
        logger.warning("USER_ACCESS_TOKEN не найден в .env. Загрузка на стену будет идти через токен группы (возможна ошибка 27).")
        return None

    _user_api = API(token.strip())
    return _user_api

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
            random_id=random.getrandbits(63)
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
                await bot_api.messages.send(peer_id=peer_id, message="Открываю гримуар...", random_id=random.getrandbits(63))
            except Exception: pass
        for _ in range(15):
            await asyncio.sleep(2)
            cached = await get_cached_photo(filename)
            if cached: return cached
        return ""
    try:
        filepath = os.path.join("cards", filename)
        if not os.path.exists(filepath):
            logger.error(f"Файл не найден: {filepath}")
            return ""

        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()
            if len(data) < 100:
                logger.warning(f"Файл {filename} слишком мал ({len(data)} байт), пропуск загрузки.")
                return ""

            photo_attachment_id = None
            last_err = None

            async with aiohttp.ClientSession() as session:
                for attempt in range(3):
                    try:
                        server = await bot_api.photos.get_messages_upload_server()

                        form = aiohttp.FormData()
                        form.add_field('photo', data, filename='photo.jpg', content_type='image/jpeg')
                        async with session.post(server.upload_url, data=form) as resp:
                            if resp.status == 504 or "text/html" in resp.headers.get("Content-Type", ""):
                                raise Exception(f"VK Server returned error/HTML (Status: {resp.status})")
                            try:
                                upload_data = await resp.json()
                            except Exception:
                                raw_text = await resp.text()
                                raise Exception(f"Invalid JSON from VK (MIME: {resp.content_type})") from None

                        saved_photos = await bot_api.request(
                            "photos.saveMessagesPhoto",
                            {
                                "photo": upload_data['photo'],
                                "server": upload_data['server'],
                                "hash": upload_data['hash']
                            }
                        )

                        if saved_photos and isinstance(saved_photos, list):
                            photo = saved_photos[0]

                            if isinstance(photo, dict):
                                owner_id = photo.get("owner_id")
                                photo_id = photo.get("id")
                                access_key = photo.get("access_key")
                            else:
                                owner_id = getattr(photo, "owner_id", None)
                                photo_id = getattr(photo, "id", None)
                                access_key = getattr(photo, "access_key", None)

                            if owner_id is not None and photo_id is not None:
                                tmp_id = f"photo{owner_id}_{photo_id}"
                                if access_key:
                                    tmp_id += f"_{access_key}"

                                photo_attachment_id = tmp_id
                                logger.debug(f"Photo uploaded successfully: {photo_attachment_id}")
                                break

                    except Exception as ex:
                        last_err = ex
                        logger.warning(f"Попытка {attempt+1} загрузки {filename} не удалась: {ex}")
                        if attempt < 2:
                            await asyncio.sleep(2)

            if photo_attachment_id:
                await _anchor_photo_and_cache(bot_api, filename, photo_attachment_id)
                return photo_attachment_id

            logger.error(f"Не удалось загрузить {filename} после 3 попыток. Последняя ошибка: {last_err}")
            return ""

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

    if not os.path.exists(os.path.join("cards", filename)):
        if "uslugi/" in filename:
            alt_filename = filename.replace("uslugi/", "")
            if os.path.exists(os.path.join("cards", alt_filename)):
                filename = alt_filename
        else:
            alt_filename = f"uslugi/{filename}"
            if os.path.exists(os.path.join("cards", alt_filename)):
                filename = alt_filename

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
        filepath = os.path.join("cards", filename)
        if not os.path.exists(filepath):
            logger.error(f"Файл не найден для wall_photo: {filepath}")
            return ""

        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()

            user_api = get_user_api()
            upload_client = user_api if user_api else bot_api

            photo_attachment_id = None
            last_err = None

            async with aiohttp.ClientSession() as session:
                for attempt in range(3):
                    try:
                        server = await upload_client.photos.get_wall_upload_server(group_id=GROUP_ID)

                        form = aiohttp.FormData()
                        form.add_field('photo', data, filename='photo.jpg', content_type='image/jpeg')
                        async with session.post(server.upload_url, data=form) as resp:
                            if resp.status == 504 or "text/html" in resp.headers.get("Content-Type", ""):
                                raise Exception(f"VK Server returned error/HTML (Status: {resp.status})")
                            try:
                                upload_data = await resp.json()
                            except Exception:
                                raw_text = await resp.text()
                                raise Exception(f"Invalid JSON from VK Wall (MIME: {resp.content_type})") from None

                        saved_photos = await upload_client.request(
                            "photos.saveWallPhoto",
                            {
                                "group_id": GROUP_ID,
                                "photo": upload_data['photo'],
                                "server": upload_data['server'],
                                "hash": upload_data['hash']
                            }
                        )

                        if saved_photos and isinstance(saved_photos, list):
                            photo = saved_photos[0]

                            if isinstance(photo, dict):
                                owner_id = photo.get("owner_id")
                                photo_id = photo.get("id")
                                access_key = photo.get("access_key")
                            else:
                                owner_id = getattr(photo, "owner_id", None)
                                photo_id = getattr(photo, "id", None)
                                access_key = getattr(photo, "access_key", None)

                            if owner_id is not None and photo_id is not None:
                                tmp_id = f"photo{owner_id}_{photo_id}"
                                if access_key:
                                    tmp_id += f"_{access_key}"

                                photo_attachment_id = tmp_id
                                logger.debug(f"Wall photo uploaded successfully: {photo_attachment_id}")
                                break

                    except Exception as ex:
                        last_err = ex
                        logger.warning(f"Попытка {attempt+1} wall_photo {filename} не удалась: {ex}")
                        if attempt < 2:
                            await asyncio.sleep(2)

            if photo_attachment_id:
                try:
                    await redis_client.set(f"wall_photo_v2:{filename}", photo_attachment_id)
                except Exception as e:
                    logger.error(f"Ошибка сохранения wall_photo в Redis: {str(e)}")
                return photo_attachment_id

            logger.error(f"Не удалось загрузить wall_photo {filename} после 3 попыток. Последняя ошибка: {last_err}")
            return ""

    except Exception as e:
        logger.error(f"Критическая ошибка при wall_photo {filename}: {str(e)}")
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
