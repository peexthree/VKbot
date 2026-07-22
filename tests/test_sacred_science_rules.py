import json
from unittest.mock import patch
import pytest
from modules.autoposter import generate_post

@pytest.mark.asyncio
async def test_sacred_science_prompt_rules():
    """Тестирует формирование промпта для научно-популярных рубрик (SACRED_SCIENCE)."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="SACRED_SCIENCE"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):

                    mock_json = {
                        "text": "Абзац 1. В 1970-х годах физик Фриц-Альберт Попп обнаружил, что живые клетки излучают слабый, но постоянный поток света — биофотоны. Это не тепловое свечение, а реальные кванты света, которые ДНК использует для мгновенной передачи команд по всему организму.\n\n"
                                "Абзац 2. Самое интригующее подтвердилось в более поздних тестах: когда две изолированные культивируемые клетки находились рядом, их световые пульсации синхронизировались. Код SACRED-123 открывает новые космические тайны.\n\n"
                                "Абзац 3. Сегодня квантовая биология вплотную подошла к тому, что древние мистики называли аурой или энергетическим телом. Это не магия, а физическая реальность: искажение биофотонного поля начинается в организме задолго до проявления первых симптомов болезней.\n\n"
                                "Абзац 4. Если наши клетки непрерывно транслируют свет в окружающее пространство, то где заканчивается наше биологическое я и начинается поле других людей? Что, если наши мысли — это тоже квантовые вспышки, способные менять структуру реальности вокруг нас?",
                        "quote": "Наше тело соткано из световых сигналов."
                    }

                    async def mock_generate_text(prompt, skin, json_mode, is_background):
                        # Проверяем, что промпт содержит новые правила для SACRED_SCIENCE
                        assert "выдающегося научного журналиста и исследователя тайн сознания" in prompt
                        assert "ОТ 700 ДО 1400 СИМВОЛОВ" in prompt
                        assert "СТРОГО 4 СМЫСЛОВЫХ БЛОКА" in prompt or "СТРОГО 4 АБЗАЦА" in prompt
                        assert "ЗАПРЕЩЕННЫЕ ИИ-ФРАЗЫ" in prompt
                        assert "В этой статье мы..." in prompt
                        return json.dumps(mock_json)

                    with patch("modules.autoposter.generate_text", side_effect=mock_generate_text):
                        post_data = await generate_post(is_morning=True, forced_rubric="SACRED_SCIENCE")
                        assert post_data is not None
                        assert "SACRED_SCIENCE" in post_data["text"] or "САКРАЛЬНАЯ НАУКА" in post_data["text"]

@pytest.mark.asyncio
async def test_global_ai_forbidden_phrases_non_targeted():
    """Тестирует, что запрет на ИИ-клише наличествует в промптах и для обычных рубрик."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="PROVOCATION"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):

                    mock_json = {
                        "text": "Обычный длинный пост для провокации..." * 20,
                        "quote": "Цитата"
                    }

                    async def mock_generate_text(prompt, skin, json_mode, is_background):
                        # Проверяем, что промпт для PROVOCATION содержит глобальный запрет, но не правила 4 абзацев
                        assert "ЗАПРЕЩЕННЫЕ ИИ-ФРАЗЫ" in prompt
                        assert "В этой статье мы..." in prompt
                        assert "ОТ 1000 ДО 2500 СИМВОЛОВ" in prompt
                        assert "СТРОГО 4 СМЫСЛОВЫХ БЛОКА" not in prompt and "СТРОГО 4 АБЗАЦА" not in prompt
                        return json.dumps(mock_json)

                    with patch("modules.autoposter.generate_text", side_effect=mock_generate_text):
                        post_data = await generate_post(is_morning=True, forced_rubric="PROVOCATION")
                        assert post_data is not None

@pytest.mark.asyncio
async def test_hidden_promo_integration_targeted_vs_normal():
    """Тестирует, что для targeted-рубрик выдается специальная инструкция по встраиванию шифра."""
    with patch("modules.autoposter.get_daily_used_content", return_value=([], [], [])):
        with patch("modules.autoposter.get_active_poll", return_value=None):
            with patch("modules.autoposter.pull_next_rubric", return_value="SACRED_SCIENCE"):
                with patch("modules.autoposter.save_hidden_promo", return_value=True):

                    # Принудительно заставляем сгенерировать промокод, подменив random.random
                    with patch("random.random", return_value=0.0):

                        mock_json = {
                            "text": "Пост с кодом..." * 40,
                            "quote": "Цитата"
                        }

                        async def mock_generate_text(prompt, skin, json_mode, is_background):
                            # Должна быть инструкция про встраивание строго во второй или третий абзац
                            assert "Ты обязан органично внедрить его СТРОГО во второй или третий абзац" in prompt or "Ты обязан органично внедрить его СТРОГО во второй или третий" in prompt
                            assert "4-абзацной структуры" in prompt or "4-смысловых блоков" in prompt or "4-смыслового" in prompt or "целостность" in prompt
                            return json.dumps(mock_json)

                        with patch("modules.autoposter.generate_text", side_effect=mock_generate_text):
                            await generate_post(is_morning=True, forced_rubric="SACRED_SCIENCE")
