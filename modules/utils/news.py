import aiohttp
import xml.etree.ElementTree as ET
from loguru import logger
import random
import re

NEWS_URLS = [
    "https://news.google.com/rss?hl=ru&gl=RU&ceid=RU:ru",
    "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=ru&gl=RU&ceid=RU:ru"
]

def clean_html(raw_html):
    """
    Removes HTML tags and entities from a string.
    """
    if not raw_html:
        return ""
    # Remove HTML tags
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    # Remove common entities
    cleantext = cleantext.replace('&nbsp;', ' ')
    # Normalize whitespace
    cleantext = ' '.join(cleantext.split())
    return cleantext

async def fetch_trending_news():
    """
    Fetches trending news from Google News RSS.
    Returns a list of dicts {"title": headline, "description": details}.
    """
    url = random.choice(NEWS_URLS)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch news: {resp.status}")
                    return []

                text = await resp.text()
                root = ET.fromstring(text)

                news_items = []
                for item in root.findall(".//item"):
                    title = item.find("title").text
                    description = item.find("description").text

                    # Usually titles are "Headline - Source"
                    if " - " in title:
                        title = title.rsplit(" - ", 1)[0]

                    news_items.append({
                        "title": title,
                        "description": clean_html(description)
                    })

                # No shuffle to keep "Top" news
                return news_items[:10]
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return []

if __name__ == "__main__":
    import asyncio
    async def test():
        news = await fetch_trending_news()
        for i, item in enumerate(news[:3]):
            print(f"{i+1}. {item['title']}\n   {item['description'][:100]}...")
    asyncio.run(test())
