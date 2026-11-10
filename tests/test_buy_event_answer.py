from unittest.mock import AsyncMock, patch

import pytest

import cache
from modules.payments.callbacks import _message_event_handler_wrapped


@pytest.mark.asyncio
async def test_buy_service_answers_event_id_exactly_once():
    cache._seen_events.clear()
    event = {
        "object": {
            "user_id": 27260796,
            "peer_id": 27260796,
            "event_id": "buy_evt_once_1",
            "payload": {"cmd": "buy", "type": "service", "key": "tarot_future"},
            "conversation_message_id": 9538,
        }
    }

    mock_user = {
        "vk_id": 27260796,
        "first_name": "Игорь",
        "balance": 5000,
        "is_registered": True,
        "purchased_sections": {},
    }

    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    mock_redis.get.return_value = None
    mock_redis.delete.return_value = True

    def fake_create_task(coro):
        coro.close()
        return None

    with (
        patch("modules.payments.callbacks.get_user", new_callable=AsyncMock, return_value=mock_user),
        patch("modules.payments.callbacks.update_user", new_callable=AsyncMock),
        patch("modules.payments.callbacks.redis_client", mock_redis),
        patch("cache.redis_client", mock_redis),
        patch("modules.payments.callbacks.acquire_lock", new_callable=AsyncMock, return_value=True),
        patch("modules.payments.callbacks.release_lock", new_callable=AsyncMock),
        patch("modules.payments.callbacks.check_throttle", new_callable=AsyncMock, return_value=False),
        patch("database.spend_user_balance", new_callable=AsyncMock, return_value=4200),
        patch("database.add_event", new_callable=AsyncMock),
        patch("modules.tarot.spreads_logic.initiate_spread_flow", new_callable=AsyncMock) as mock_init_spread,
        patch("modules.payments.callbacks.asyncio.create_task", side_effect=fake_create_task),
        patch("modules.payments.callbacks.bot.api.request", new_callable=AsyncMock, return_value={"response": 1}) as mock_vk_request,
    ):
        await _message_event_handler_wrapped(event)

    answer_calls = [
        c for c in mock_vk_request.call_args_list if c.args and c.args[0] == "messages.sendMessageEventAnswer"
    ]
    assert len(answer_calls) == 1
    mock_init_spread.assert_awaited_once()


@pytest.mark.asyncio
async def test_buy_insufficient_balance_answers_once_and_reaches_payment_screen():
    cache._seen_events.clear()
    event = {
        "object": {
            "user_id": 27260796,
            "peer_id": 27260796,
            "event_id": "buy_evt_once_2",
            "payload": {"cmd": "buy", "type": "tariff", "key": "tariff_1"},
            "conversation_message_id": 9539,
        }
    }

    mock_user = {
        "vk_id": 27260796,
        "first_name": "Игорь",
        "balance": 100,
        "is_registered": True,
        "free_teaser_used": True,
        "purchased_sections": {},
    }

    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    mock_redis.get.return_value = None
    mock_redis.delete.return_value = True

    def fake_create_task(coro):
        coro.close()
        return None

    with (
        patch("modules.payments.callbacks.get_user", new_callable=AsyncMock, return_value=mock_user),
        patch("modules.payments.callbacks.update_user", new_callable=AsyncMock),
        patch("modules.payments.callbacks.redis_client", mock_redis),
        patch("cache.redis_client", mock_redis),
        patch("modules.payments.callbacks.acquire_lock", new_callable=AsyncMock, return_value=True),
        patch("modules.payments.callbacks.release_lock", new_callable=AsyncMock),
        patch("modules.payments.callbacks.check_throttle", new_callable=AsyncMock, return_value=False),
        patch("modules.payments.yookassa.create_yookassa_payment", new_callable=AsyncMock, return_value="https://yookassa.ru/pay/123"),
        patch("modules.payments.callbacks.ghost_edit", new_callable=AsyncMock) as mock_ghost_edit,
        patch("modules.payments.callbacks.asyncio.create_task", side_effect=fake_create_task),
        patch("modules.payments.callbacks.bot.api.request", new_callable=AsyncMock, return_value={"response": 1}) as mock_vk_request,
    ):
        await _message_event_handler_wrapped(event)

    answer_calls = [
        c for c in mock_vk_request.call_args_list if c.args and c.args[0] == "messages.sendMessageEventAnswer"
    ]
    assert len(answer_calls) == 1
    mock_ghost_edit.assert_awaited_once()
    assert "НЕДОСТАТОЧНО ЭНЕРГИИ" in mock_ghost_edit.call_args.kwargs["message"]
