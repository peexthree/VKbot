from typing import Optional, List
from loguru import logger
from database.config import URL, KEY, HEADERS
import database.core as core

async def save_feedback(user_id: int, service_name: str, rating: int, comment: Optional[str] = None):
    """Сохраняет отзыв в таблицу feedbacks"""
    if not URL or not KEY or core.session is None:
        return None

    payload = {
        "user_id": user_id,
        "service_name": service_name,
        "rating": rating,
        "comment": comment,
        "is_posted": False
    }

    try:
        async with core.session.post(f"{URL}/rest/v1/feedbacks", headers=HEADERS, json=payload) as r:
            if r.status in (200, 201):
                data = await r.json()
                if data:
                    logger.success(f"✅ Сохранен отзыв от {user_id} для {service_name}: {rating}*")
                    return data[0]
            else:
                text = await r.text()
                logger.error(f"Supabase feedbacks error: {r.status} - {text}")
    except Exception as e:
        logger.error(f"Ошибка в save_feedback: {e}")
    return None

async def get_last_feedbacks(limit: int = 5):
    """Получает последние N отзывов из таблицы feedbacks"""
    if not URL or not KEY or core.session is None:
        return []

    params = {
        "order": "created_at.desc",
        "limit": str(limit)
    }

    try:
        async with core.session.get(f"{URL}/rest/v1/feedbacks", headers=HEADERS, params=params) as r:
            if r.status == 200:
                return await r.json()
            else:
                text = await r.text()
                logger.error(f"Supabase feedbacks error: {r.status} - {text}")
    except Exception as e:
        logger.error(f"Ошибка в get_last_feedbacks: {e}")
    return []

async def get_unposted_feedbacks(limit: int = 4):
    """Получает неопубликованные отзывы"""
    if not URL or not KEY or core.session is None:
        return []

    params = {
        "is_posted": "eq.false",
        "order": "created_at.asc",
        "limit": str(limit)
    }

    try:
        async with core.session.get(f"{URL}/rest/v1/feedbacks", headers=HEADERS, params=params) as r:
            if r.status == 200:
                return await r.json()
            else:
                text = await r.text()
                logger.error(f"Supabase get_unposted_feedbacks error: {r.status} - {text}")
    except Exception as e:
        logger.error(f"Ошибка в get_unposted_feedbacks: {e}")
    return []

async def mark_feedbacks_as_posted(feedback_ids: List[int]):
    """Помечает отзывы как опубликованные"""
    if not URL or not KEY or core.session is None or not feedback_ids:
        return False

    # Формируем строку для фильтра in.
    ids_str = ",".join(map(str, feedback_ids))

    params = {
        "id": f"in.({ids_str})"
    }

    payload = {
        "is_posted": True
    }

    try:
        async with core.session.patch(f"{URL}/rest/v1/feedbacks", headers=HEADERS, params=params, json=payload) as r:
            if r.status in (200, 204):
                logger.success(f"✅ Отзывы {feedback_ids} помечены как опубликованные")
                return True
            else:
                text = await r.text()
                logger.error(f"Supabase mark_feedbacks_as_posted error: {r.status} - {text}")
    except Exception as e:
        logger.error(f"Ошибка в mark_feedbacks_as_posted: {e}")
    return False
