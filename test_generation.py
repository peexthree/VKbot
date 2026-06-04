import asyncio
import os
import sys
from loguru import logger

# Mocking bot and other things
os.environ["VK_TOKEN"] = "dummy"
os.environ["GROUP_ID"] = "219181948"

from modules.autoposter import generate_post
from database.core import init_db, close_db

async def test():
    await init_db()
    try:
        print("Testing post generation...")
        post = await generate_post()
        if post:
            print("SUCCESS! Generated post content:")
            print("-" * 20)
            print(f"Topic: {post['topic']}")
            print(f"Character: {post['skin_id']}")
            print(f"Text snippet: {post['text'][:100]}...")
            print("-" * 20)
        else:
            print("FAILED! No post generated.")
    except Exception as e:
        print(f"ERROR during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(test())
