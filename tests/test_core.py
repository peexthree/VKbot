from __future__ import annotations
import os
from unittest.mock import MagicMock, patch

import pytest


def test_generate_premium_pdf():
    from modules.utils import generate_premium_pdf

    # We create a dummy html to ensure weasyprint works with it
    # ensure templates folder exists for the test
    if not os.path.exists('templates'):
        os.makedirs('templates')

    # Mock weasyprint HTML since it requires external dependencies (cairo/pango)
    # that might fail in some test environments, but we'll try to just patch it if needed.
    with patch('weasyprint.HTML') as mock_html:
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
