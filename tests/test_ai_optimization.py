import json
import pytest
from unittest.mock import patch
from ai.sections import extract_tags, extract_birth_data, generate_section

@pytest.mark.asyncio
async def test_extract_tags():
    # Тест на извлечение тегов из фиксированного списка
    text = "Я хочу найти любовь и обрести финансовое благополучие."
    mock_response = '["поиск-любви", "гармония-в-финансах"]'

    with patch("ai.sections.generate_text", return_value=mock_response) as mock_gen:
        tags = await extract_tags(text)
        assert isinstance(tags, list)
        assert "поиск-любви" in tags
        assert "гармония-в-финансах" in tags
        for tag in tags:
            from ai.sections import AVAILABLE_TAGS
            assert tag in AVAILABLE_TAGS
        mock_gen.assert_called_once()

@pytest.mark.asyncio
async def test_extract_birth_data_complete():
    text = "Я родился 15 апреля 1990 в 14:30 в Москве"
    mock_response = '{"date": "15.04.1990", "time": "14:30", "city": "Москва", "is_complete": true}'

    with patch("ai.sections.generate_text", return_value=mock_response):
        data = await extract_birth_data(text)
        assert data["is_complete"] is True
        assert data["date"] == "15.04.1990"
        assert data["city"] == "Москва"

@pytest.mark.asyncio
async def test_extract_birth_data_partial():
    text = "Я из Питера, родился в 1985 году"
    # Эмулируем нормализацию городом в ответе ИИ
    mock_response = '{"date": "01.01.1985", "time": "12:00", "city": "Санкт-Петербург", "is_complete": true}'

    with patch("ai.sections.generate_text", return_value=mock_response):
        data = await extract_birth_data(text)
        assert data["city"] == "Санкт-Петербург"
        assert data["is_complete"] is True

@pytest.mark.asyncio
async def test_generate_section_raw_text():
    # Тест на то, что хиромантия возвращает строку (не JSON)
    mock_response = "ХИРОМАНТИЯ\n\nВаш разбор..."

    with patch("ai.sections.generate_text", return_value=mock_response):
        res = await generate_section(
            section="palmistry",
            date="15.04.1990",
            time="12:00",
            city="Москва",
            return_json=True
        )
        assert isinstance(res, str)
        assert "ХИРОМАНТИЯ" in res.upper()

@pytest.mark.asyncio
async def test_generate_section_json():
    # Тест на то, что обычная секция возвращает валидный JSON (dict)
    mock_data = {
        "text": "Ваш разбор...",
        "next_activation_date": "15.05.2024",
        "activation_level": 85
    }
    mock_response = json.dumps(mock_data)

    with patch("ai.sections.generate_text", return_value=mock_response):
        res = await generate_section(
            section="base",
            date="15.04.1990",
            time="12:00",
            city="Москва",
            return_json=True,
            current_date="01.01.2024"
        )
        assert isinstance(res, dict)
        assert res["text"] == "Ваш разбор..."
        assert "2024" in res["next_activation_date"]
