import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest
from modules.payments.callbacks import _message_event_handler_wrapped


@pytest.mark.asyncio
async def test_unregistered_user_callback_interception():
    # Simulate callback click event on main_menu
    event = {
        "object": {
            "user_id": 999999,
            "peer_id": 999999,
            "event_id": "test_unreg_event_1",
            "payload": {"cmd": "main_menu"},
            "conversation_message_id": 1234,
        }
    }

    # User is not registered
    mock_user = {
        "vk_id": 999999,
        "first_name": "Новичок",
        "balance": 0,
        "is_registered": False,
        "purchased_sections": {},
    }

    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    mock_redis.get.return_value = None

    with (
        patch("modules.payments.callbacks.get_user", return_value=mock_user),
        patch("modules.payments.callbacks.redis_client", mock_redis),
        patch("modules.payments.callbacks.acquire_lock", return_value=True),
        patch("modules.payments.callbacks.release_lock", new_callable=AsyncMock),
        patch("modules.payments.callbacks.bot.api.request", new_callable=AsyncMock) as mock_vk_request,
        patch("modules.registration.start_handler", new_callable=AsyncMock) as mock_start_handler,
    ):
        mock_vk_request.return_value = {"response": 1}
        await _message_event_handler_wrapped(event)

        # Should answer event with a warning snackbar
        mock_vk_request.assert_called_once()
        args, kwargs = mock_vk_request.call_args
        method = args[0]
        params = args[1] if len(args) > 1 else kwargs.get("params")
        assert method == "messages.sendMessageEventAnswer"
        event_data = json.loads(params.get("event_data", "{}"))
        assert event_data.get("type") == "show_snackbar"
        assert "Пожалуйста, заверши настройку" in event_data.get("text", "")

        # Should redirect to start_handler
        mock_start_handler.assert_called_once()


@pytest.mark.asyncio
async def test_unregistered_user_skin_selection_redirection():
    # Simulate selecting a skin when unregistered
    mock_user = {
        "vk_id": 999999,
        "first_name": "Новичок",
        "balance": 0,
        "is_registered": False,
        "purchased_sections": {},
    }

    from modules.profile.settings import process_skin_action_logic

    with (
        patch("modules.profile.settings.get_user", return_value=mock_user),
        patch("modules.profile.settings.update_user", new_callable=AsyncMock) as mock_update,
        patch("modules.profile.settings.acquire_lock", return_value=True),
        patch("modules.profile.settings.release_lock", new_callable=AsyncMock),
        patch("modules.registration.process_onboarding_skin_logic", new_callable=AsyncMock) as mock_onboarding_logic,
    ):
        payload = {"cmd": "set_skin", "skin": "sheps_alex"}
        await process_skin_action_logic(
            vk_id=999999,
            peer_id=999999,
            skip_lock=True,
            payload=payload,
            conversation_message_id=5678
        )

        # Should update active skin
        mock_update.assert_called_once()
        update_args = mock_update.call_args[0][1]
        assert update_args.get("active_skin") == "sheps_alex"

        # Should redirect to process_onboarding_skin_logic instead of show_profile_logic
        mock_onboarding_logic.assert_called_once_with(999999, 999999, "sheps_alex", conversation_message_id=5678)
