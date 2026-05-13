import sys
from unittest.mock import MagicMock

# Mock dependencies
sys.modules["aiohttp"] = MagicMock()
sys.modules["loguru"] = MagicMock()
sys.modules["configs"] = MagicMock()
sys.modules["configs.models"] = MagicMock()
sys.modules["cards_data"] = MagicMock()
sys.modules["prompts"] = MagicMock()
sys.modules["prompts.base"] = MagicMock()
sys.modules["prompts.personas"] = MagicMock()
sys.modules["cache"] = MagicMock()

import asyncio
import pytest
from unittest.mock import patch

# Now import ai_service
import ai_service

@pytest.fixture(autouse=True)
def reset_cache():
    ai_service._cached_api_keys = None
    yield
    ai_service._cached_api_keys = None

def run_async(coro):
    return asyncio.run(coro)

def test_get_gemini_api_keys_empty():
    with patch.dict("os.environ", {}, clear=True):
        keys = run_async(ai_service.get_gemini_api_keys())
        assert keys == []

def test_get_gemini_api_keys_single():
    with patch.dict("os.environ", {"GEMINI_API_KEY": "key1"}, clear=True):
        keys = run_async(ai_service.get_gemini_api_keys())
        assert keys == ["key1"]

def test_get_gemini_api_keys_multiple_in_keys_env():
    with patch.dict("os.environ", {"GEMINI_API_KEYS": "key1,key2, key3 "}, clear=True):
        keys = run_async(ai_service.get_gemini_api_keys())
        assert keys == ["key1", "key2", "key3"]

def test_get_gemini_api_keys_fallback():
    # GEMINI_API_KEYS is empty, fallback to GEMINI_API_KEY
    with patch.dict("os.environ", {"GEMINI_API_KEYS": "", "GEMINI_API_KEY": "key_fallback"}, clear=True):
        keys = run_async(ai_service.get_gemini_api_keys())
        assert keys == ["key_fallback"]

def test_get_gemini_api_keys_caching():
    with patch.dict("os.environ", {"GEMINI_API_KEY": "key1"}, clear=True):
        keys1 = run_async(ai_service.get_gemini_api_keys())
        assert keys1 == ["key1"]

    # Change env, but should return cached
    with patch.dict("os.environ", {"GEMINI_API_KEY": "key2"}, clear=True):
        keys2 = run_async(ai_service.get_gemini_api_keys())
        assert keys2 == ["key1"]

def test_get_gemini_api_keys_extra_commas():
    with patch.dict("os.environ", {"GEMINI_API_KEYS": ",key1,, key2,"}, clear=True):
        keys = run_async(ai_service.get_gemini_api_keys())
        assert keys == ["key1", "key2"]
