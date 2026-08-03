import sys
import importlib
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

# Восстанавливаем оригинальный модуль database.autoposter, если он был замокан в других тестах (например, в test_autoposter_news.py)
if "database.autoposter" in sys.modules:
    if isinstance(sys.modules["database.autoposter"], (MagicMock, AsyncMock)):
        del sys.modules["database.autoposter"]

import database.autoposter
importlib.reload(database.autoposter)

from database.autoposter import add_community_post
from modules.utils.photos import extract_max_size_url
from modules.autoposter import post_to_vk

# 1. Тест извлечения URL максимального разрешения из разных форматов объектов VK
def test_extract_max_size_url():
    # Случай 1: Словарь со списком размеров
    photo_dict = {
        "sizes": [
            {"width": 100, "height": 100, "url": "url_small"},
            {"width": 800, "height": 600, "url": "url_large"},
            {"width": 400, "height": 300, "url": "url_medium"}
        ]
    }
    assert extract_max_size_url(photo_dict) == "url_large"

    # Случай 2: Объект (vkbottle модель) с атрибутом sizes
    class MockSize:
        def __init__(self, w, h, u):
            self.width = w
            self.height = h
            self.url = u

    class MockPhoto:
        def __init__(self, sizes_list):
            self.sizes = sizes_list

    photo_obj = MockPhoto([
        MockSize(130, 130, "u1"),
        MockSize(1200, 800, "u2"),
        MockSize(600, 400, "u3")
    ])
    assert extract_max_size_url(photo_obj) == "u2"

    # Случай 3: Сломанный/пустой объект
    assert extract_max_size_url(None) == ""
    assert extract_max_size_url({}) == ""


# 2. Тест функции отправки в Supabase (add_community_post)
@pytest.mark.asyncio
async def test_add_community_post_rest_api():
    # Настраиваем MagicMock для имитации асинхронного контекстного менеджера сессии aiohttp
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 201

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    mock_session.post.return_value = mock_context

    with patch("database.autoposter.core.session", mock_session), \
         patch("database.autoposter.URL", "https://mocksupabase.co"), \
         patch("database.autoposter.KEY", "mock_key"):

        # Вызов функции
        res = await add_community_post(vk_post_id=9999, text="Тестовый текст", image_url="https://vk.cdn/img.jpg")

        # Проверяем возвращаемое значение
        assert res is True

        # Проверяем, что был вызван POST на правильный URL с правильными заголовками
        mock_session.post.assert_called_once()
        args, kwargs = mock_session.post.call_args
        assert args[0] == "https://mocksupabase.co/rest/v1/community_posts?on_conflict=vk_post_id"

        # Проверяем Prefer заголовок upsert
        headers = kwargs.get("headers", {})
        assert "resolution=merge-duplicates" in headers.get("Prefer", "")

        # Проверяем тело запроса
        json_body = kwargs.get("json", {})
        assert json_body["vk_post_id"] == 9999
        assert json_body["text"] == "Тестовый текст"
        assert json_body["image_url"] == "https://vk.cdn/img.jpg"
        assert "published_at" in json_body


# 3. Тест интеграции сохранения постов в post_to_vk
@pytest.mark.asyncio
async def test_post_to_vk_sync_integration():
    long_ai_text = "Это очень глубокий и развернутый разбор. " * 20 # 800 символов
    mock_post_data = {
        "text": "РУБРИКА: ПРОВОКАЦИЯ\n\n" + long_ai_text,
        "ai_text": long_ai_text,
        "skin_id": "olesya",
        "rubric": "PROVOCATION",
        "topic": "Тема",
        "quote": "Цитата"
    }

    # Мокаем все шаги автопостинга
    with patch("modules.autoposter.generate_post", return_value=mock_post_data), \
         patch("modules.autoposter.bot.api.request", new_callable=AsyncMock) as mock_vk_request, \
         patch("modules.autoposter.upload_wall_photo", return_value="photo-123_456_key"), \
         patch("modules.autoposter.redis.get", new_callable=AsyncMock) as mock_redis_get, \
         patch("modules.autoposter.redis.set", new_callable=AsyncMock) as mock_redis_set, \
         patch("modules.autoposter.add_community_post") as mock_add_community_post, \
         patch("modules.autoposter.add_post_history"):

        # Настраиваем ответы на VK запросы (wall.post, wall.create_comment)
        mock_vk_request.side_effect = [
            {"response": {"post_id": 7878}}, # wall.post
            {"response": {"comment_id": 123}} # wall.create_comment
        ]

        # Настраиваем возвращение URL картинки из Redis для аплоада
        mock_redis_get.return_value = b"https://vk.cdn/mock_photo.jpg"

        # Запускаем автопостинг
        await post_to_vk(is_morning=True)

        # Проверяем, что add_community_post был вызван с правильными параметрами
        mock_add_community_post.assert_called_once()
        args, kwargs = mock_add_community_post.call_args
        assert kwargs.get("vk_post_id") == 7878
        assert kwargs.get("text") == "РУБРИКА: ПРОВОКАЦИЯ\n\n" + long_ai_text
        assert kwargs.get("image_url") == "https://vk.cdn/mock_photo.jpg"
