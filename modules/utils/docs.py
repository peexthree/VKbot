import os
import asyncio
import aiofiles
from loguru import logger
async def upload_pdf_to_vk(bot_api, filepath: str, title: str, peer_id: int) -> str:
    """
    Загрузка PDF-документа в ВК с механизмом повторных попыток.
    Решает проблему VKAPIError_100 (file is undefined) при docs.save.
    """
    if not os.path.exists(filepath):
        logger.error(f"Файл не найден для загрузки: {filepath}")
        return ""

    try:
        last_err = None

        for attempt in range(3):
            try:
                # Читаем файл в память, чтобы избежать проблем с дескрипторами при повторах
                async with aiofiles.open(filepath, 'rb') as f:
                    data = await f.read()

                if not data:
                    logger.error(f"Файл {filepath} пуст.")
                    return ""

                # 1. Получаем сервер загрузки
                server = await bot_api.docs.get_messages_upload_server(type="doc", peer_id=peer_id)

                # 2. Загружаем файл
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    form = aiohttp.FormData()
                    form.add_field('file', data, filename=title)
                    async with session.post(server.upload_url, data=form) as resp:
                        upload_data = await resp.json()

                # 3. Сохраняем через сырой запрос для обхода валидации vkbottle.
                res_data = await bot_api.request(
                    "docs.save",
                    {
                        "file": upload_data['file'],
                        "title": title
                    }
                )

                # Развертывание ответа: docs.save возвращает структуру {"response": {"type": "doc", "doc": {...}}}
                if res_data:
                    # 1. Извлекаем response, если ВК вернул сырой dict
                    if isinstance(res_data, dict) and "response" in res_data:
                        res_data = res_data["response"]

                    # 2. Ищем данные самого документа (ВК упаковывает их в ключ "doc")
                    doc_info = None
                    if isinstance(res_data, dict):
                        if "doc" in res_data:
                            doc_info = res_data["doc"]
                        elif "id" in res_data:  # на случай, если пришел уже развернутый объект
                            doc_info = res_data

                    # 3. Собираем и строго возвращаем строку вложения
                    if doc_info and isinstance(doc_info, dict):
                        owner_id = doc_info.get("owner_id")
                        doc_id = doc_info.get("id")

                        if owner_id is not None and doc_id is not None:
                            attachment = f"doc{owner_id}_{doc_id}"
                            access_key = doc_info.get("access_key")
                            if access_key:
                                attachment += f"_{access_key}"

                            logger.success(f"Документ {title} успешно загружен в ВК (попытка {attempt+1}): {attachment}")
                            return attachment
            except Exception as e:
                last_err = e
                logger.warning(f"Попытка {attempt+1} загрузки документа {title} (peer_id={peer_id}) не удалась: {e}")
                # Увеличиваем задержку между попытками
                await asyncio.sleep(1.5 * (attempt + 1))

        logger.error(f"Не удалось загрузить документ {title} после 3 попыток. Последняя ошибка: {last_err}")
        return ""
    finally:
        # Локальный PDF-файл удаляется в блоке finally после завершения всей цепочки попыток
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.error(f"Ошибка при удалении временного файла {filepath}: {e}")
