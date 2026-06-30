import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from modules.autoposter import generate_post, post_to_vk

@pytest.mark.asyncio
async def test_viral_post_generation():
    # Мокаем БД
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # Мокаем AI
                    mock_json = {
                        "text": "Тестовый пост. #АнтиТар",
                        "quote": "Таро — это костыль."
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)

                        assert post_data is not None
                        assert "text" in post_data
                        assert post_data["quote"] == "Таро — это костыль."
                        assert "PROVOCATION" in post_data["text"] or "ПРОВОКАЦИЯ" in post_data["text"]

@pytest.mark.asyncio
async def test_sunday_mechanics():
    # Мокаем текущую дату на воскресенье
    sunday = MagicMock()
    sunday.weekday.return_value = 6
    sunday.strftime.return_value = "07.07.2024"

    with patch("datetime.datetime") as mock_date:
        mock_date.now.return_value = sunday
        # На самом деле в коде используется now = datetime.datetime.now(tz_bash)
        # Нам нужно убедиться что logic подхватит is_sunday

        with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
            with patch("modules.autoposter.get_active_poll", return_value=None):
                with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                    with patch("modules.autoposter.save_hidden_promo", return_value=True):
                        mock_json = {
                            "text": "Текст с ЧАСТЬ1. #АнтиТар",
                            "quote": "Цитата"
                        }
                        with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                            post_data = await generate_post(is_morning=True)
                            assert post_data["is_sunday"] is True

if __name__ == "__main__":
    asyncio.run(test_viral_post_generation())
    asyncio.run(test_sunday_mechanics())
    print("Tests passed!")
