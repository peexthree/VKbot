import os
import logging
import aiohttp

logger = logging.getLogger(__name__)

async def send_verification_email(email: str, code: str = None) -> bool:
    """
    Инициирует отправку 6-значного текстового OTP кода (без ссылок) через Supabase.
    Запрос идет по HTTPS (порт 443), обходя любые блокировки SMTP портов Render.
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

    if not supabase_url or not supabase_key:
        logger.warning("Отправка невозможна: SUPABASE_URL или SUPABASE_KEY не заданы!")
        return False

    # Используем официальный эндпоинт Supabase для отправки голых OTP токенов на почту
    url = f"{supabase_url}/auth/v1/otp"

    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": "application/json"
    }

    payload = {
        "email": email,
        "create_user": True  # Если юзера нет в Auth-базе, Supabase создаст его автоматически
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=10) as response:
                if response.status in (200, 201):
                    logger.info(f"Запрос на генерацию и отправку текстового OTP успешно принят Supabase для {email}.")
                    return True

                error_body = await response.text()
                logger.error(f"Supabase OTP API вернул ошибку {response.status}: {error_body}")
                return False

    except Exception as e:
        logger.error(f"Исключение при вызове Supabase OTP: {e}")
        return False


async def verify_email_otp(email: str, token: str) -> bool:
    """
    Проверяет введённый пользователем OTP код через API Supabase.
    Запрос идет по HTTPS (порт 443) на эндпоинт POST /auth/v1/verify
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

    if not supabase_url or not supabase_key:
        logger.warning("Верификация невозможна: SUPABASE_URL или SUPABASE_KEY не заданы!")
        return False

    url = f"{supabase_url}/auth/v1/verify"

    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": "application/json"
    }

    payload = {
        "email": email,
        "token": token,
        "type": "email"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=10) as response:
                if response.status in (200, 201):
                    logger.info(f"OTP успешно верифицирован Supabase для {email}.")
                    return True

                error_body = await response.text()
                logger.error(f"Supabase Verify API вернул ошибку {response.status}: {error_body}")
                return False

    except Exception as e:
        logger.error(f"Исключение при верификации Supabase OTP: {e}")
        return False
