import pytest
import asyncio
from unittest.mock import patch, MagicMock

import os

def test_generate_premium_pdf():
    from modules.utils import generate_premium_pdf

    # We create a dummy html to ensure weasyprint works with it
    # ensure templates folder exists for the test
    if not os.path.exists('templates'):
        os.makedirs('templates')

    # Mock weasyprint HTML since it requires external dependencies (cairo/pango)
    # that might fail in some test environments, but we'll try to just patch it if needed.
    with patch('modules.utils.HTML') as mock_html:
        mock_instance = MagicMock()
        mock_html.return_value = mock_instance

        result = generate_premium_pdf(
            user_name="TestUser",
            birth_info="01.01.2000 Moscow",
            section_name="TEST SECTION",
            text_content="This is a test content\nNew line.",
            output_filename="test_output.pdf",
            card_id=None
        )

        assert result is True
        mock_html.assert_called_once()
        mock_instance.write_pdf.assert_called_once_with("test_output.pdf")

@pytest.mark.asyncio
async def test_money_transfer_handler_idempotency():
    from modules.payments import money_transfer_handler

    event_payload = {
        "group_id": 219181948,
        "object": {
            "from_id": 123456789,
            "amount": 100
        },
        "event_id": "test_event_123"
    }

    # In money_transfer_handler there's an import inside the function: `from cache import acquire_lock`
    # We need to mock cache.acquire_lock, not modules.payments.acquire_lock
    with patch('modules.bot_init.bot.api.messages.send') as mock_send:
        # First call - simulate successful lock acquisition and then returning early
        with patch('modules.payments.acquire_lock', return_value=True) as mock_lock:
            with patch('modules.payments.check_and_save_transaction', return_value=True) as mock_check:
                with patch('modules.payments.get_user', return_value=None) as mock_get_user:
                    await money_transfer_handler(event_payload)
                    mock_lock.assert_called_once_with("tx_vkpay_123456789_100_test_event_123", ttl=3600)
                    mock_check.assert_called_once_with("tx_vkpay_123456789_100_test_event_123", 123456789, 0)
                    mock_get_user.assert_called_once_with(123456789)

        # Second call - simulate lock acquisition failure (duplicate)
        with patch('modules.payments.acquire_lock', return_value=False) as mock_lock:
            with patch('modules.payments.check_and_save_transaction') as mock_check:
                with patch('modules.payments.get_user') as mock_get_user:
                    await money_transfer_handler(event_payload)
                    mock_lock.assert_called_once_with("tx_vkpay_123456789_100_test_event_123", ttl=3600)
                    mock_check.assert_not_called()
                    mock_get_user.assert_not_called() # Should return before calling DB

from unittest.mock import AsyncMock, patch, MagicMock
from cache import check_throttle

@pytest.mark.asyncio
async def test_check_throttle():
    with patch("cache.redis_client.set", new_callable=AsyncMock) as mock_set:
        mock_set.return_value = True
        is_throttled = await check_throttle(123)
        assert is_throttled is False

        mock_set.return_value = None
        is_throttled = await check_throttle(123)
        assert is_throttled is True

@pytest.mark.asyncio
async def test_get_user():
    from database import get_user

    with patch("database.URL", "http://mock.supabase"), \
         patch("database.KEY", "mock_key"):

        mock_session = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_response = AsyncMock()

        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[{"vk_id": 123, "balance": 10}])

        # Setup context manager correctly for async with
        mock_ctx_mgr.__aenter__.return_value = mock_response
        mock_ctx_mgr.__aexit__.return_value = None
        mock_session.get.return_value = mock_ctx_mgr

        with patch("database.session", mock_session):
            user = await get_user(123)
            assert user is not None
            assert user["vk_id"] == 123
            assert user["balance"] == 10

@pytest.mark.asyncio
async def test_show_balance():
    from modules.profile import show_balance

    with patch("modules.profile.get_user", new_callable=AsyncMock) as mock_get_user, \
         patch("database.set_user_state", new_callable=AsyncMock) as mock_set_state:

         mock_get_user.return_value = {"balance": 450}

         mock_msg = MagicMock()
         mock_msg.from_id = 123
         mock_msg.answer = AsyncMock()

         await show_balance(mock_msg)

         mock_set_state.assert_called_with(123, "")
         mock_msg.answer.assert_called_with("ТВОЙ ТЕКУЩИЙ БАЛАНС: 450 Энергии звезд")
