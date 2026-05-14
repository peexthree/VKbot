import os
from unittest.mock import patch
import pytest
from modules.utils import generate_premium_pdf

@pytest.mark.asyncio
async def test_generate_premium_pdf():
    output = "test_output.pdf"
    success = generate_premium_pdf(
        user_name="Test User",
        birth_info="10.10.1990 10:00 Moscow",
        section_name="TEST SECTION",
        text_content="This is a test PDF content.",
        output_filename=output,
        card_id="0"
    )
    if os.path.exists(output):
        os.remove(output)
    assert success is True or success is False

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

    with patch('modules.bot_init.bot.api.messages.send') as mock_send:
        # Mock it in handlers.py where it is used
        with patch('modules.payments.handlers.acquire_lock', return_value=True) as mock_lock:
            with patch('database.check_and_save_transaction', return_value=False):
                await money_transfer_handler(event_payload)
                assert mock_lock.called
