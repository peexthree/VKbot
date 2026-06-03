import datetime
from typing import List
from loguru import logger
from database.config import URL, KEY, HEADERS
import database.core as core

async def get_recent_topics(limit: int = 30) -> List[str]:
    """Возвращает список последних опубликованных тем"""
    if not URL or not KEY or core.session is None: return []
    try:
        url = f"{URL}/rest/v1/post_history?select=topic_name&order=published_at.desc&limit={limit}"
        async with core.session.get(url, headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return [item["topic_name"] for item in data]
    except Exception as e:
        logger.error(f"Error in get_recent_topics: {e}")
    return []

async def add_post_history(topic_name: str):
    """Записывает публикацию поста в историю"""
    if not URL or not KEY or core.session is None: return False
    payload = {
        "topic_name": topic_name,
        "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    try:
        async with core.session.post(f"{URL}/rest/v1/post_history", headers=HEADERS, json=payload) as r:
            return r.status in (200, 201, 204)
    except Exception as e:
        logger.error(f"Error in add_post_history: {e}")
    return False

async def record_post_click(vk_id: int, topic_name: str):
    """Записывает клик пользователя и инкрементирует общий счетчик темы"""
    if not URL or not KEY or core.session is None: return False

    # 1. Записываем детальный клик
    click_payload = {
        "vk_id": vk_id,
        "topic_name": topic_name,
        "clicked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    try:
        # Пишем клик
        await core.session.post(f"{URL}/rest/v1/post_clicks", headers=HEADERS, json=click_payload)

        # 2. Инкрементируем счетчик в post_history через RPC (рекомендуется)
        # Если RPC нет, можно попробовать PATCH, но нужно найти ID последнего поста с этой темой
        # Давай попробуем RPC, это надежнее
        await core.call_rpc("increment_post_clicks", {"p_topic_name": topic_name})

        return True
    except Exception as e:
        logger.error(f"Error in record_post_click: {e}")
    return False
