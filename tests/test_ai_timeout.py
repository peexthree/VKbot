import asyncio
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from ai import logic


@pytest.mark.asyncio
async def test_generate_text_switches_model_immediately_on_timeout():
    calls: list[tuple[str, float]] = []

    class FakeResp:
        def __init__(self, text: str):
            self.status = 200
            self._text = text

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}

    class FakeSession:
        def post(self, url, json=None, timeout=None):
            calls.append((url, timeout.total))
            if "model-slow" in url:
                raise asyncio.TimeoutError()
            return FakeResp("Ответ от резервной модели")

    with (
        patch("ai.logic.get_gemini_api_keys", new_callable=AsyncMock, return_value=["k1", "k2"]),
        patch("ai.logic.get_system_config", new_callable=AsyncMock, return_value="0"),
        patch("ai.logic.acquire_ai_slot", new_callable=AsyncMock, return_value=True),
        patch("ai.logic.init_session", return_value=FakeSession()),
        patch("ai.logic.MODELS", [("models/model-slow", "v1beta"), ("models/model-fast", "v1beta")]),
    ):
        result = await logic.generate_text("Сделай глубокий расклад", is_background=False)

    assert result == "Ответ от резервной модели"
    # model-slow вызывалась ровно 1 раз (без повтора и без перебора k2 после таймаута)
    slow_calls = [c for c in calls if "model-slow" in c[0]]
    fast_calls = [c for c in calls if "model-fast" in c[0]]
    assert len(slow_calls) == 1
    assert len(fast_calls) == 1
    assert slow_calls[0][1] == 40
    assert fast_calls[0][1] == 40


@pytest.mark.asyncio
async def test_generate_text_retries_client_error_once():
    calls: list[str] = []

    class FakeResp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Успех после сбоя"}]}}]}

    class FakeSession:
        def post(self, url, json=None, timeout=None):
            calls.append(url)
            if len(calls) == 1:
                raise aiohttp.ClientConnectionError("reset by peer")
            return FakeResp()

    with (
        patch("ai.logic.get_gemini_api_keys", new_callable=AsyncMock, return_value=["k1"]),
        patch("ai.logic.get_system_config", new_callable=AsyncMock, return_value="0"),
        patch("ai.logic.acquire_ai_slot", new_callable=AsyncMock, return_value=True),
        patch("ai.logic.init_session", return_value=FakeSession()),
        patch("ai.logic.asyncio.sleep", new_callable=AsyncMock),
        patch("ai.logic.FAST_LITE_MODELS", [("models/model-lite", "v1beta")]),
        patch("ai.logic.MODELS", [("models/model-lite", "v1beta")]),
    ):
        result = await logic.generate_text("Тест", is_background=True)

    assert result == "Успех после сбоя"
    assert len(calls) == 2
