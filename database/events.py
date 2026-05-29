import datetime
from typing import Any, Dict, Optional
from loguru import logger
from database.config import URL, KEY, HEADERS
import database.core as core

async def add_event(user_id: int, action: str, metadata: Optional[Dict[str, Any]] = None):
    if not URL or not KEY or core.session is None: return False
    payload = {
        "user_id": user_id,
        "action": action,
        "metadata": metadata or {},
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    try:
        async with core.session.post(f"{URL}/rest/v1/events", headers=HEADERS, json=payload) as r:
            return r.status in (200, 201, 204)
    except Exception as e:
        logger.error(f"Error adding event {action} for {user_id}: {e}")
        return False

async def is_first_payment(user_id: int) -> bool:
    if not URL or not KEY or core.session is None: return True
    try:
        # Check for any existing payment events
        async with core.session.get(
            f"{URL}/rest/v1/events?user_id=eq.{user_id}&action=in.('energy_purchased','first_payment','vkpay_transaction')",
            headers=HEADERS
        ) as r:
            if r.status == 200:
                data = await r.json()
                return len(data) == 0
    except Exception as e:
        logger.error(f"Error checking first payment for {user_id}: {e}")
    return True
