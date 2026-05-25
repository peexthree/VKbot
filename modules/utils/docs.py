import os
import asyncio
import aiofiles
from loguru import logger
from vkbottle import DocMessagesUploader

async def upload_pdf_to_vk(bot_api, filepath: str, title: str, peer_id: int) -> str:
    """
    Загрузка PDF-документа в ВК с механизмом повторных попыток.
    Решает проблему VKAPIError_100 (file is undefined) при docs.save.
    """
    if not os.path.exists(filepath):
        logger.error(f"Файл не найден для загрузки: {filepath}")
        return ""

    uploader = DocMessagesUploader(bot_api)
    last_err = None

    for attempt in range(3):
        try:
            # Читаем файл в память, чтобы избежать проблем с дескрипторами при повторах
            async with aiofiles.open(filepath, 'rb') as f:
                data = await f.read()

            if not data:
                logger.error(f"Файл {filepath} пуст.")
                return ""

            # Загружаем документ
            doc = await uploader.upload(title=title, file_source=data, peer_id=peer_id)
            if doc:
                logger.success(f"Документ {title} успешно загружен в ВК (попытка {attempt+1})")
                return doc
        except Exception as e:
            last_err = e
            logger.warning(f"Попытка {attempt+1} загрузки документа {title} (peer_id={peer_id}) не удалась: {e}")
            # Увеличиваем задержку между попытками
            await asyncio.sleep(1.5 * (attempt + 1))

    logger.error(f"Не удалось загрузить документ {title} после 3 попыток. Последняя ошибка: {last_err}")
    return ""
