import pytest
import re
from unittest.mock import AsyncMock, patch, MagicMock

EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

def test_email_validation():
    # Валидные email-адреса
    assert re.match(EMAIL_REGEX, "test@example.com") is not None
    assert re.match(EMAIL_REGEX, "user.name+tag@mail.ru") is not None
    assert re.match(EMAIL_REGEX, "123@domain.org") is not None

    # Невалидные email-адреса
    assert re.match(EMAIL_REGEX, "invalid_email") is None
    assert re.match(EMAIL_REGEX, "@example.com") is None
    assert re.match(EMAIL_REGEX, "test@.com") is None
    assert re.match(EMAIL_REGEX, "test@com") is None


@pytest.mark.asyncio
async def test_send_verification_email_success():
    from modules.utils.email_sender import send_verification_email

    # Мокаем aiohttp.ClientSession и метод post
    mock_response = AsyncMock()
    mock_response.status = 200

    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)

    mock_session_instance = MagicMock()
    mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
    mock_session_instance.__aexit__ = AsyncMock(return_value=None)
    mock_session_instance.post = MagicMock(return_value=mock_context_manager)

    with patch("aiohttp.ClientSession", return_value=mock_session_instance), patch.dict("os.environ", {
        "SUPABASE_URL": "https://test-project.supabase.co",
        "SUPABASE_KEY": "test_service_role_key"
    }):
        res = await send_verification_email("user@example.com", "123456")
        assert res is True

        # Проверяем, что post был вызван с правильными параметрами
        mock_session_instance.post.assert_called_once_with(
            "https://test-project.supabase.co/auth/v1/invite",
            headers={
                "apikey": "test_service_role_key",
                "Authorization": "Bearer test_service_role_key",
                "Content-Type": "application/json"
            },
            json={
                "email": "user@example.com",
                "data": {
                    "code": "123456"
                }
            },
            timeout=10
        )


@pytest.mark.asyncio
async def test_send_verification_email_failure():
    from modules.utils.email_sender import send_verification_email

    # Мокаем aiohttp.ClientSession и метод post с кодом ошибки 400
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.text = AsyncMock(return_value="Email already invited or invalid")

    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context_manager.__aexit__ = AsyncMock(return_value=None)

    mock_session_instance = MagicMock()
    mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
    mock_session_instance.__aexit__ = AsyncMock(return_value=None)
    mock_session_instance.post = MagicMock(return_value=mock_context_manager)

    with patch("aiohttp.ClientSession", return_value=mock_session_instance), patch.dict("os.environ", {
        "SUPABASE_URL": "https://test-project.supabase.co",
        "SUPABASE_KEY": "test_service_role_key"
    }):
        res = await send_verification_email("user@example.com", "123456")
        assert res is False
