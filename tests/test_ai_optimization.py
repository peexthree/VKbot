import pytest
from ai.sections import extract_tags, extract_birth_data, generate_section
from ai.core import init_session, close_session

@pytest.fixture(autouse=True)
async def session_manager():
    init_session()
    yield
    await close_session()

@pytest.mark.asyncio
async def test_extract_tags():
    # Тест на извлечение тегов из фиксированного списка
    text = "Я хочу найти любовь и обрести финансовое благополучие."
    tags = await extract_tags(text)
    assert isinstance(tags, list)
    if tags:
        for tag in tags:
            from ai.sections import AVAILABLE_TAGS
            assert tag in AVAILABLE_TAGS

@pytest.mark.asyncio
async def test_extract_birth_data_complete():
    text = "Я родился 15 апреля 1990 в 14:30 в Москве"
    data = await extract_birth_data(text)
    assert data["is_complete"] is True
    assert data["date"] == "15.04.1990"
    assert data["city"] == "Москва"

@pytest.mark.asyncio
async def test_extract_birth_data_partial():
    text = "Я из Питера, родился в 1985 году"
    data = await extract_birth_data(text)
    # ИИ может вернуть разное в зависимости от модели, но мы ожидаем нормализацию если город найден
    if data["city"]:
        assert data["city"] == "Санкт-Петербург"
    assert data["is_complete"] in [True, False]

@pytest.mark.asyncio
async def test_generate_section_raw_text():
    # Тест на то, что хиромантия возвращает строку (не JSON)
    res = await generate_section(
        section="palmistry",
        date="15.04.1990",
        time="12:00",
        city="Москва",
        return_json=True # Даже если просим JSON, должно вернуть строку
    )
    assert isinstance(res, str)
    assert "ХИРОМАНТИЯ" in res.upper()

@pytest.mark.asyncio
async def test_generate_section_json():
    # Тест на то, что обычная секция возвращает валидный JSON (dict)
    res = await generate_section(
        section="base",
        date="15.04.1990",
        time="12:00",
        city="Москва",
        return_json=True,
        current_date="01.01.2024"
    )
    assert isinstance(res, dict)
    assert "text" in res
    assert "next_activation_date" in res
    # Проверка года в следующей активации (должен быть 2024 или 2025)
    date_str = res["next_activation_date"]
    assert ("2024" in date_str or "2025" in date_str)
