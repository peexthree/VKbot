from typing import Any, Dict, Optional
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
        "comment": comment
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
