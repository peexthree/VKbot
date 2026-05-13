import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
import sys

# Mocking modules before any imports from the project
mock_loguru = MagicMock()
sys.modules["loguru"] = mock_loguru

mock_vkbottle = MagicMock()
sys.modules["vkbottle"] = mock_vkbottle
sys.modules["vkbottle.bot"] = mock_vkbottle

# Mock internal modules
sys.modules["cache"] = MagicMock()
sys.modules["database"] = MagicMock()
sys.modules["modules.bot_init"] = MagicMock()
sys.modules["modules.utils"] = MagicMock()
sys.modules["modules.states"] = MagicMock()

# Now we can import the functions from profile.py
# We use patch to ensure that any other dependencies are handled
with patch("modules.bot_init.bot"), \
     patch("database.update_user"), \
     patch("database.set_user_state"), \
     patch("cache.acquire_lock"), \
     patch("cache.release_lock"):
    from modules.profile import process_change_date, process_change_time, process_change_city

@pytest.mark.asyncio
async def test_process_change_date_validation():
    mock_msg = AsyncMock()
    mock_msg.from_id = 12345

    # Valid date
    mock_msg.text = "15.04.1990"
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.set_user_state") as mock_set_state, \
         patch("modules.profile.release_lock"):
        await process_change_date(mock_msg)
        mock_set_state.assert_called_with(12345, json.dumps({"step": "time", "date": "15.04.1990"}))
        mock_msg.answer.assert_called_with("Дата 15.04.1990 принята. Теперь введите ВРЕМЯ вашего рождения (например, 14:30 или 'не знаю'):")

    # Invalid format
    mock_msg.text = "15-04-1990"
    mock_msg.answer.reset_mock()
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.release_lock"):
        await process_change_date(mock_msg)
        mock_msg.answer.assert_called_with("ФОРМАТ ОТКЛОНЕН. Введите дату строго в формате ДД.ММ.ГГГГ (например, 15.04.1990).")

    # Invalid date (logical)
    mock_msg.text = "32.01.1990"
    mock_msg.answer.reset_mock()
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.release_lock"):
        await process_change_date(mock_msg)
        mock_msg.answer.assert_called_with("ДАТА НЕДЕЙСТВИТЕЛЬНА. Введите существующую дату в формате ДД.ММ.ГГГГ.")

@pytest.mark.asyncio
async def test_process_change_time_validation():
    mock_msg = AsyncMock()
    mock_msg.from_id = 12345

    # Valid time
    mock_msg.text = "14:30"
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.get_fsm_step", return_value={"date": "15.04.1990"}), \
         patch("modules.profile.set_user_state") as mock_set_state, \
         patch("modules.profile.release_lock"):
        await process_change_time(mock_msg)
        mock_set_state.assert_called_with(12345, json.dumps({"step": "city", "date": "15.04.1990", "time": "14:30"}))
        mock_msg.answer.assert_called_with("Время 14:30 принято. Теперь введите ГОРОД вашего рождения:")

    # "не знаю"
    mock_msg.text = "не знаю"
    mock_msg.answer.reset_mock()
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.get_fsm_step", return_value={"date": "15.04.1990"}), \
         patch("modules.profile.set_user_state") as mock_set_state, \
         patch("modules.profile.release_lock"):
        await process_change_time(mock_msg)
        mock_set_state.assert_called_with(12345, json.dumps({"step": "city", "date": "15.04.1990", "time": "12:00"}))

    # Invalid time
    mock_msg.text = "25:00"
    mock_msg.answer.reset_mock()
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.release_lock"):
        await process_change_time(mock_msg)
        mock_msg.answer.assert_called_with("ФОРМАТ ОТКЛОНЕН. Введите время в формате ЧЧ:ММ (например, 14:30) или напишите 'не знаю'.")

@pytest.mark.asyncio
async def test_process_change_city_validation():
    mock_msg = AsyncMock()
    mock_msg.from_id = 12345

    # Valid city
    mock_msg.text = "Москва"
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.get_fsm_step", return_value={"date": "15.04.1990", "time": "14:30"}), \
         patch("modules.profile.update_user") as mock_update, \
         patch("modules.profile.set_user_state"), \
         patch("modules.profile.release_lock"):
        await process_change_city(mock_msg)
        mock_update.assert_called_with(12345, {
            "birth_date": "15.04.1990",
            "birth_time": "14:30",
            "birth_city": "Москва"
        })

    # Too short
    mock_msg.text = "М"
    mock_msg.answer.reset_mock()
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.release_lock"):
        await process_change_city(mock_msg)
        mock_msg.answer.assert_called_with("ФОРМАТ ОТКЛОНЕН. Название города должно быть от 2 до 50 символов.")

    # Invalid characters
    mock_msg.text = "Москва123"
    mock_msg.answer.reset_mock()
    with patch("modules.profile.acquire_lock", return_value=True), \
         patch("modules.profile.release_lock"):
        await process_change_city(mock_msg)
        mock_msg.answer.assert_called_with("ФОРМАТ ОТКЛОНЕН. Название города может содержать только буквы, пробелы и дефисы.")
