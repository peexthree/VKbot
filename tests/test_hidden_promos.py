import pytest
from unittest.mock import AsyncMock
from modules.profile.views import apply_promo_logic

@pytest.mark.asyncio
async def test_apply_promo_logic_hidden_cipher_success(mocker):
    # Мокаем зависимости
    mock_message = AsyncMock()
    mock_message.text = "MATRIX-707"
    mock_message.peer_id = 123

    mock_user = {"vk_id": 123, "balance": 100, "purchased_sections": {}}

    # Мокаем вызовы к БД
    mocker.patch("modules.profile.views.acquire_lock", return_value=True)
    mocker.patch("modules.profile.views.release_lock", return_value=True)
    mocker.patch("modules.profile.views.set_user_state", return_value=None)
    mocker.patch("modules.profile.views.start_dynamic_typing", return_value=None)
    mocker.patch("modules.profile.views.stop_dynamic_typing", return_value=456)

    # Главный мок для RPC
    mock_rpc = mocker.patch("database.call_rpc", new_callable=AsyncMock)
    mock_rpc.return_value = {
        "status": "success",
        "reward": 500,
        "current_uses": 1,
        "max_uses": 10
    }

    # Запускаем логику
    await apply_promo_logic(123, mock_message)

    # Проверяем вызов RPC
    mock_rpc.assert_called_once_with("activate_hidden_promo", {"p_user_id": 123, "p_code": "MATRIX-707"})

    # Проверяем ответ пользователю
    expected_msg = "🔮 Система зафиксировала ввод ключа дешифрации. Ты успешно активировал скрытый шифр и забираешь +500 энергии ⚡. Ты был 1-м по счету (осталось 9 активаций). Матрица запомнила твой код."
    mock_message.answer.assert_called_once_with(expected_msg)

@pytest.mark.asyncio
async def test_apply_promo_logic_hidden_cipher_limit_reached(mocker):
    mock_message = AsyncMock()
    mock_message.text = "FAIL-111"
    mock_message.peer_id = 123

    mocker.patch("modules.profile.views.acquire_lock", return_value=True)
    mocker.patch("modules.profile.views.release_lock", return_value=True)
    mocker.patch("modules.profile.views.set_user_state", return_value=None)
    mocker.patch("modules.profile.views.start_dynamic_typing", return_value=None)
    mocker.patch("modules.profile.views.stop_dynamic_typing", return_value=None)

    mock_rpc = mocker.patch("database.call_rpc", new_callable=AsyncMock)
    mock_rpc.return_value = {
        "status": "error",
        "code": "LIMIT_REACHED"
    }

    await apply_promo_logic(123, mock_message)

    expected_msg = "👹 Опоздал. Скрытый код полностью выжжен и уничтожен. 10 человек оказались быстрее, внимательнее и голоднее тебя. В следующий раз включай уведомления на посты и не спи, когда вселенная раздает ресурсы."
    mock_message.answer.assert_called_once_with(expected_msg)
