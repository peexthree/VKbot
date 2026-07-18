import os
import aiohttp
from loguru import logger

async def send_verification_email(email: str, code: str) -> bool:
    """
    Отправляет приглашение (код подтверждения) на Email через Supabase Auth REST API.
    Код передается в user_metadata под ключом 'code'.
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_KEY", "")

    if not supabase_url or not supabase_key:
        logger.warning("SUPABASE_URL or SUPABASE_KEY is not configured in .env!")
        return False

    url = f"{supabase_url}/auth/v1/invite"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": email,
        "data": {
            "code": code
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=10) as response:
                if response.status in (200, 201):
                    logger.success(f"Verification email requested via Supabase for {email}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to send email via Supabase to {email}: {response.status} - {error_text}")
                    return False
    except Exception as e:
        logger.error(f"Exception during sending email via Supabase to {email}: {e}")
        return False
