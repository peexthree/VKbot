import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_rpm_limiter_logic():
    # Mock redis_client
    with patch("cache.redis_client") as mock_redis:
        from cache import acquire_ai_slot
        # Mock eval for Lua script
        # Return 1 for first 2 calls, then 0
        mock_redis.eval = AsyncMock(side_effect=[1, 1, 0])

        # 1. Success calls
        res1 = await acquire_ai_slot(limit=2, wait=False)
        assert res1 is True

        res2 = await acquire_ai_slot(limit=2, wait=False)
        assert res2 is True

        # 3. Blocked call
        res3 = await acquire_ai_slot(limit=2, wait=False)
        assert res3 is False

@pytest.mark.asyncio
async def test_rpm_limiter_wait():
    with patch("cache.redis_client") as mock_redis:
        from cache import acquire_ai_slot
        # Return 0 then 1
        mock_redis.eval = AsyncMock(side_effect=[0, 1])

        # We need to mock asyncio.sleep so it doesn't actually wait
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            res = await acquire_ai_slot(limit=1, wait=True)
            assert res is True
            assert mock_sleep.call_count == 1

@pytest.mark.asyncio
async def test_generate_text_uses_limiter():
    # Mock everything generate_text needs before it hits the network or redis
    with patch("ai.logic.get_gemini_api_keys", new_callable=AsyncMock) as mock_keys, \
         patch("cache.redis_client") as mock_redis, \
         patch("cache.acquire_ai_slot", new_callable=AsyncMock) as mock_acquire:

        mock_keys.return_value = ["key1"]
        mock_redis.get = AsyncMock(return_value=b"1") # proxy_enabled
        mock_acquire.return_value = False # Simulate limit hit

        from ai.logic import generate_text
        # Should return ERROR_RPM_LIMIT if wait=False (is_background=False)
        res = await generate_text("test", is_background=False)
        assert res == "ERROR_RPM_LIMIT"
        assert mock_acquire.called
