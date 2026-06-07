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

            # 3. Сохраняем через сырой запрос для обхода валидации vkbottle. vkbottle.request возвращает содержимое 'response'
            res_data = await bot_api.request(
                "docs.save",
                {
                    "file": upload_data['file'],
                    "title": title
                }
            )

            # docs.save может возвращать объект или список в зависимости от типа
            if isinstance(res_data, list):
                doc_obj = res_data[0] if res_data else None
            elif isinstance(res_data, dict):
                # В случае docs.save для документов часто возвращается словарь с типом (например {'type': 'doc', 'doc': {...}})
                doc_obj = res_data.get("doc") or res_data
            else:
                doc_obj = None

            if doc_obj:
                owner_id = doc_obj.get("owner_id")
                doc_id = doc_obj.get("id")
                # Формируем строку аттачмента
                attachment = f"doc{owner_id}_{doc_id}"
                if doc_obj.get("access_key"):
                    attachment += f"_{doc_obj['access_key']}"

                logger.success(f"Документ {title} успешно загружен в ВК (попытка {attempt+1})")
                return attachment
        except Exception as e:
            last_err = e
            logger.warning(f"Попытка {attempt+1} загрузки документа {title} (peer_id={peer_id}) не удалась: {e}")
            # Увеличиваем задержку между попытками
            await asyncio.sleep(1.5 * (attempt + 1))

    logger.error(f"Не удалось загрузить документ {title} после 3 попыток. Последняя ошибка: {last_err}")
    return ""
