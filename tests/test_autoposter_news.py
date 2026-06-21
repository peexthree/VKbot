import asyncio
from unittest.mock import MagicMock, AsyncMock

# Mocking modules before imports
import sys
mock_db = MagicMock()
mock_db.autoposter = AsyncMock()
mock_db.autoposter.get_daily_used_content = AsyncMock(return_value=([], [], []))
mock_db.autoposter.get_active_poll = AsyncMock(return_value=None)
mock_db.autoposter.close_poll = AsyncMock()
mock_db.autoposter.add_post_history = AsyncMock()
mock_db.autoposter.save_active_poll = AsyncMock()
sys.modules["database.autoposter"] = mock_db.autoposter

# Mock generate_text to see the prompt
import ai_service
async def mock_gen(prompt, skin=None):
    print("\n--- DEBUG PROMPT ---")
    print(prompt)
    print("--- END DEBUG PROMPT ---\n")
    return "MOCK AI RESPONSE"

ai_service.generate_text = AsyncMock(side_effect=mock_gen)

# Mock fetch_trending_news to return empty list to test fallback
import modules.utils.news
modules.utils.news.fetch_trending_news = AsyncMock(return_value=[])

from modules.autoposter import generate_post

async def test_news_post():
    print("Testing evening post (NEWS_BREAKDOWN)...")
    post_data = await generate_post(is_morning=False)

    if post_data:
        print(f"Rubric: {post_data['rubric']}")
        print(f"Topic: {post_data['topic']}")
        print(f"Skin: {post_data['skin_id']}")
        print("-" * 20)
        print(post_data['text'])
        print("-" * 20)
    else:
        print("Failed to generate post")

if __name__ == "__main__":
    asyncio.run(test_news_post())
