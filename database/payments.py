import datetime
from loguru import logger
from database.config import URL, KEY, HEADERS
import database.core as core

async def is_payment_processed(payment_id: str) -> bool:
    """Проверяет, был ли платеж уже обработан (защита от дублей)"""
    if not URL or not KEY or core.session is None: return False
    try:
        async with core.session.get(f"{URL}/rest/v1/processed_payments?payment_id=eq.{payment_id}", headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return len(data) > 0
    except Exception as e:
        logger.error(f"Error checking payment {payment_id}: {e}")
    return False

async def mark_payment_as_processed(payment_id: str):
    """Помечает платеж как обработанный"""
    if not URL or not KEY or core.session is None: return False
    payload = {
        "payment_id": payment_id,
        "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    try:
        async with core.session.post(f"{URL}/rest/v1/processed_payments", headers=HEADERS, json=payload) as r:
            return r.status in (200, 201, 204)
    except Exception as e:
        logger.error(f"Error marking payment {payment_id} as processed: {e}")
        return False
