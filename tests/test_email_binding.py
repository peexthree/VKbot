import pytest
import re
from unittest.mock import AsyncMock, MagicMock, patch

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
@patch("smtplib.SMTP_SSL")
async def test_send_verification_email(mock_smtp):
    from modules.utils.email_sender import send_verification_email

    # Настраиваем мок SMTP сервера
    mock_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_instance

    with patch.dict("os.environ", {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "465",
        "SMTP_USER": "bot@example.com",
        "SMTP_PASSWORD": "secret_password",
        "SMTP_FROM": "bot@example.com"
    }):
        res = await send_verification_email("user@example.com", "123456")
        assert res is True
        mock_instance.login.assert_called_once_with("bot@example.com", "secret_password")
        mock_instance.sendmail.assert_called_once()
