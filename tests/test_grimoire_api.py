import os
import json
import pytest
import hashlib
import hmac
import base64
from aiohttp import web
from unittest.mock import AsyncMock, patch

# Импортируем функции для тестирования
import main

def compute_vk_sign(params_dict, secret):
    """Вспомогательная функция для генерации подписи как в VK"""
    # Фильтруем параметры: только те, что начинаются на vk_,
    # исключая vk_share_ и vk_group_
    sorted_keys = sorted([
        k for k in params_dict.keys()
        if k.startswith("vk_") and not k.startswith("vk_share_") and not k.startswith("vk_group_")
    ])
    check_str = "&".join([f"{k}={params_dict[k]}" for k in sorted_keys])

    hash_code = hmac.new(
        secret.encode("utf-8"),
        check_str.encode("utf-8"),
        hashlib.sha256
    ).digest()

    expected_sign = base64.b64encode(hash_code).decode("utf-8")
    expected_sign = expected_sign.replace("+", "-").replace("/", "_").rstrip("=")
    return expected_sign

@pytest.fixture
def mock_user():
    return {
        "vk_id": 12345,
        "readings_history": [
            {"title": "First", "date": "01.01.2024", "text": "Old prediction"},
            {"title": "Second", "date": "02.01.2024", "text": "🃏 Маг — Мастерство\nNew prediction"}
        ]
    }

@pytest.fixture
def vk_params_valid():
    secret = "test_secret"
    params_dict = {
        "vk_user_id": "12345",
        "vk_app_id": "123",
        "vk_platform": "desktop"
    }
    sign = compute_vk_sign(params_dict, secret)

    query_str = "&".join([f"{k}={v}" for k, v in params_dict.items()])
    return f"{query_str}&sign={sign}"

@pytest.mark.asyncio
async def test_handle_grimoire_success(mock_user, vk_params_valid):
    os.environ["VK_MINI_APP_SECRET"] = "test_secret"

    with patch("database.get_user", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = mock_user

        # Создаем мок запроса
        request = AsyncMock(spec=web.Request)
        request.headers = {"X-VK-Params": vk_params_valid}
        request.method = "GET"

        response = await main.handle_grimoire(request)

        assert response.status == 200
        data = json.loads(response.body)

        assert len(data) == 2
        # Сортировка: новые (последние в списке) должны быть первыми
        assert data[0]["title"] == "Маг"
        assert data[0]["date"] == "02.01.2024"
        assert "New prediction" in data[0]["text"]

        assert data[1]["title"] == "First"
        assert data[1]["date"] == "01.01.2024"
        assert data[1]["text"] == "Old prediction"

        # Проверка наличия ID
        assert "id" in data[0]
        assert "id" in data[1]
        assert data[0]["id"] != data[1]["id"]

@pytest.mark.asyncio
async def test_handle_grimoire_invalid_sign(vk_params_valid):
    os.environ["VK_MINI_APP_SECRET"] = "wrong_secret"

    request = AsyncMock(spec=web.Request)
    request.headers = {"X-VK-Params": vk_params_valid}
    request.method = "GET"

    response = await main.handle_grimoire(request)
    assert response.status == 403
    data = json.loads(response.body)
    assert data["error"] == "Invalid signature"

@pytest.mark.asyncio
async def test_handle_grimoire_missing_params():
    request = AsyncMock(spec=web.Request)
    request.headers = {}
    request.method = "GET"

    response = await main.handle_grimoire(request)
    assert response.status == 400
    data = json.loads(response.body)
    assert data["error"] == "Missing X-VK-Params header"
