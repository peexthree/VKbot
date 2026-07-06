import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from modules.autoposter import handle_diagnosis_comment

@pytest.mark.asyncio
async def test_handle_diagnosis_comment_with_date():
    event = {
        "object": {
            "text": "Моя дата 01.01.1990, вскрой меня",
            "from_id": 12345,
            "post_id": 67890,
            "id": 111
        }
    }

    # Мокаем БД и AI
    mock_user = {"vk_id": 12345, "balance": 1000, "birth_city": "Москва"}
    with patch("database.get_user", return_value=mock_user):
        with patch("modules.autoposter.generate_text", return_value="Твой диагноз: ты слишком серьезен.") as mock_gen:
            # Нам нужно мокать bot.api.request, потому что vkbottle.api вызывает его
            with patch("modules.autoposter.bot.api.request", new_callable=AsyncMock) as mock_request:
                # vkbottle ожидает объект с полем response
                mock_request.return_value = {"response": {"comment_id": 999}}
                res = await handle_diagnosis_comment(event)

                assert res is None
                mock_gen.assert_called_once()
                # 2 calls: users.get and wall.createComment
                assert mock_request.call_count == 2

                # Check createComment call (last one)
                args, kwargs = mock_request.call_args_list[-1]
                assert args[0].lower() in ["wall.create_comment", "wall.createcomment"]
                assert "Твой диагноз" in args[1]["message"]

@pytest.mark.asyncio
async def test_handle_diagnosis_comment_no_date():
    event = {
        "object": {
            "text": "Просто комментарий без даты",
            "from_id": 12345,
            "post_id": 67890,
            "id": 111
        }
    }

    with patch("database.get_user") as mock_get_user:
        res = await handle_diagnosis_comment(event)
        assert res is None
        mock_get_user.assert_not_called()

if __name__ == "__main__":
    asyncio.run(test_handle_diagnosis_comment_with_date())
    asyncio.run(test_handle_diagnosis_comment_no_date())
    print("Comment handler tests passed!")
