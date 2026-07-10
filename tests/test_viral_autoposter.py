import asyncio
import json
from unittest.mock import patch, MagicMock
import pytest
from modules.autoposter import generate_post

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
async def test_hashtag_handling_clean():
    """Тестирует правильность извлечения хэштегов и непопадание обычных слов в хэштеги."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # 1. Сценарий с явно выделенными хэштегами в конце
                    mock_json_1 = {
                        "text": "Ты жаришь хлеб в реакторе\n#АнтиТар #Судьба",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json_1)):
                        post_data_1 = await generate_post(is_morning=True)
                        assert "#АнтиТар #Судьба" in post_data_1["text"]
                        assert "Ты жаришь хлеб в реакторе" in post_data_1["text"]

                    # 2. Сценарий с обычным текстом в конце (без хэштегов)
                    mock_json_2 = {
                        "text": "Ты жаришь хлеб в реакторе\nИ это очень странно.",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json_2)):
                        post_data_2 = await generate_post(is_morning=True)
                        assert "И это очень странно." in post_data_2["text"]
                        assert "#АнтиТар #МатрицаСудьбы #Психология #Судьба" in post_data_2["text"]

@pytest.mark.asyncio
async def test_hashtag_handling_punctuation_and_deduplication():
    """Тестирует обратное сканирование, очистку знаков препинания из хэштегов и дедупликацию."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):
                    # Сценарий с грязными хэштегами и дубликатами в конце
                    mock_json = {
                        "text": "Тело поста.\n\n#АнтиТар, #Психология. #Судьба! #антитар #МатрицаСудьбы...",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json)):
                        post_data = await generate_post(is_morning=True)
                        text = post_data["text"]

                        # Хэштеги должны быть очищены от знаков препинания
                        # Из-за дедупликации без учета регистра, #антитар должен остаться только один раз
                        assert "#АнтиТар #Психология #Судьба #МатрицаСудьбы" in text
                        assert "#АнтиТар, " not in text
                        assert "#Психология." not in text
                        assert "#антитар" not in text.split("Чтобы взломать")[1] # В финальной части только первый дедуплицированный
                        assert "Тело поста." in text

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

@pytest.mark.asyncio
async def test_dynamic_cta_handling():
    """Тестирует детекцию динамического CTA (эмодзи 🔮) и пропуск жесткого навигатора."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.get_least_recent_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):

                    # 1. Сценарий, когда ИИ сгенерировал динамический CTA с 🔮 в конце
                    mock_json_with_cta = {
                        "text": "Тело поста. Разрушаем иллюзии.\n\n🔮 Хватит кормить чужих демонов... Нажимай на кнопку Написать сообществу...\n#АнтиТар #МатрицаСудьбы",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json_with_cta)):
                        post_data = await generate_post(is_morning=True)
                        text = post_data["text"]

                        # Должен быть динамический CTA
                        assert "🔮 Хватит кормить чужих демонов... Нажимай на кнопку Написать сообществу..." in text
                        # Жесткого навигатора быть НЕ должно
                        assert "Чтобы взломать свою судьбу" not in text

                    # 2. Сценарий, когда ИИ забыл выдать концовку с 🔮
                    mock_json_no_cta = {
                        "text": "Тело поста. Разрушаем иллюзии без призывов.\n#АнтиТар #МатрицаСудьбы",
                        "quote": "Цитата"
                    }
                    with patch("modules.autoposter.generate_text", return_value=json.dumps(mock_json_no_cta)):
                        post_data = await generate_post(is_morning=True)
                        text = post_data["text"]

                        # Жесткий навигатор ДОЛЖЕН быть приклеен
                        assert "Чтобы взломать свою судьбу и получить доступ к скрытым настройкам души, нажми кнопку Написать сообществу и бот тебя проведет по лучшему пути" in text

if __name__ == "__main__":
    asyncio.run(test_viral_post_generation())
    asyncio.run(test_sunday_mechanics())
    asyncio.run(test_dynamic_cta_handling())
    print("Tests passed!")
