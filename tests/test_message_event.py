import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from modules.payments.callbacks import _message_event_handler_wrapped


@pytest.mark.asyncio
async def test_message_event_handler_main_menu():
    # Simulate callback click event
    event = {
        "object": {
            "user_id": 27260796,
            "peer_id": 27260796,
            "event_id": "test_event_12345",
            "payload": {"cmd": "main_menu"},
            "conversation_message_id": 9538,
        }
    }

    mock_user = {
        "vk_id": 27260796,
        "first_name": "Игорь",
        "balance": 18451,
        "active_skin": "olesya",
        "visit_streak": 17,
        "purchased_sections": {},
    }

    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    mock_redis.get.return_value = None

    # Mock DB functions
    with (
        patch("modules.payments.callbacks.get_user", return_value=mock_user),
        patch(
            "modules.payments.callbacks.update_user", new_callable=AsyncMock
        ) as mock_update,
        patch("modules.payments.callbacks.redis_client", mock_redis),
        patch("modules.payments.callbacks.acquire_lock", return_value=True),
        patch(
            "modules.payments.callbacks.release_lock", new_callable=AsyncMock
        ) as mock_release_lock,
        patch("modules.payments.callbacks.check_throttle", return_value=False),
        patch("modules.utils.logic.acquire_lock", return_value=True),
        patch(
            "modules.payments.callbacks.bot.api.request", new_callable=AsyncMock
        ) as mock_vk_request,
        patch(
            "modules.payments.callbacks.upload_local_photo",
            return_value="photo-1234_5678",
        ),
    ):
        # We need mock_vk_request to return successful response for message event answer and messages delete / send
        mock_vk_request.return_value = {"response": 1}

        # Run the handler
        await _message_event_handler_wrapped(event)

        # Ensure redis lock set was called to answer the event to prevent timeout spinner
        mock_redis.set.assert_any_call(
            "event_answered:test_event_12345", "1", ex=30, nx=True
        )

        # Verify database interaction
        mock_update.assert_called()

        # Lock released at the end
        mock_release_lock.assert_called_once_with(27260796)


if __name__ == "__main__":
    asyncio.run(test_message_event_handler_main_menu())
    print("Message event handler test passed!")
