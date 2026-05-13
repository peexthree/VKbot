import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

# Mock dependencies that are not available to allow ai_service to be imported
# We explicitly set __spec__ on mocks because vkbottle's dependencies (choicelib)
# might use importlib.util.find_spec on them, which fails if __spec__ is missing.
def mock_if_missing(module_name):
    try:
        __import__(module_name)
    except ImportError:
        mock_mod = MagicMock()
        mock_mod.__spec__ = MagicMock()
        sys.modules[module_name] = mock_mod

missing_deps = [
    "aiohttp", "loguru", "configs", "configs.models",
    "cards_data", "prompts", "prompts.base",
    "prompts.personas", "cache"
]

for dep in missing_deps:
    mock_if_missing(dep)

import pytest
import ai_service

@pytest.fixture(autouse=True)
def reset_cache():
    ai_service._cached_api_keys = None
    yield
    ai_service._cached_api_keys = None

def test_get_gemini_api_keys_empty():
    with patch.dict("os.environ", {}, clear=True):
        keys = asyncio.run(ai_service.get_gemini_api_keys())
        assert keys == []

def test_get_gemini_api_keys_single():
    with patch.dict("os.environ", {"GEMINI_API_KEY": "key1"}, clear=True):
        keys = asyncio.run(ai_service.get_gemini_api_keys())
        assert keys == ["key1"]

def test_get_gemini_api_keys_multiple_in_keys_env():
    with patch.dict("os.environ", {"GEMINI_API_KEYS": "key1,key2, key3 "}, clear=True):
        keys = asyncio.run(ai_service.get_gemini_api_keys())
        assert keys == ["key1", "key2", "key3"]

def test_get_gemini_api_keys_fallback():
    # GEMINI_API_KEYS is empty, fallback to GEMINI_API_KEY
    with patch.dict("os.environ", {"GEMINI_API_KEYS": "", "GEMINI_API_KEY": "key_fallback"}, clear=True):
        keys = asyncio.run(ai_service.get_gemini_api_keys())
        assert keys == ["key_fallback"]

def test_get_gemini_api_keys_caching():
    with patch.dict("os.environ", {"GEMINI_API_KEY": "key1"}, clear=True):
        keys1 = asyncio.run(ai_service.get_gemini_api_keys())
        assert keys1 == ["key1"]

    # Change env, but should return cached
    with patch.dict("os.environ", {"GEMINI_API_KEY": "key2"}, clear=True):
        keys2 = asyncio.run(ai_service.get_gemini_api_keys())
        assert keys2 == ["key1"]

def test_get_gemini_api_keys_extra_commas():
    with patch.dict("os.environ", {"GEMINI_API_KEYS": ",key1,, key2,"}, clear=True):
        keys = asyncio.run(ai_service.get_gemini_api_keys())
        assert keys == ["key1", "key2"]
