import aiohttp
import xml.etree.ElementTree as ET
from loguru import logger
import random
import re

# Тематические неполитические фиды Google News
NEWS_URLS = [
    "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=ru&gl=RU&ceid=RU:ru",
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ru&gl=RU&ceid=RU:ru",
    "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=ru&gl=RU&ceid=RU:ru",
    "https://news.google.com/rss/headlines/section/topic/HEALTH?hl=ru&gl=RU&ceid=RU:ru"
]

# Жесткий стоп-лист тем для первичной фильтрации (в нижнем регистре для быстрого поиска)
BLACK_LIST_WORDS = [
    # Военная и геополитическая тематика
    "сво", "бпла", "прилет", "боевые действия", "взрыв", "фронт", "ракетный удар", "конфликт", "санкции",
    "война", "теракт", "погиб", "военный", "армия", "оборона", "обстрел", "атака", "беспилотник", "дрон",
    "снаряд", "пленный", "оружие", "мобилизац", "вс рф", "всу", "минобороны", "оккупац", "ядерн",
    # Имена политиков и государственные деятели
    "трамп", "байден", "путин", "зеленский", "шольц", "макрон", "песков", "госдума", "кремль", "белый дом",
    "правительств", "министр", "конгресс", "сенат", "выборы", "депутат", "политик",
    # Тяжелые тревожные метафоры и темы
    "стальные птицы смерти", "струны гильотины", "агония мира", "апокалипсис", "кровь на асфальте", "запах гари",
    "катастрофа", "трагедия", "смерть", "убит", "жертв", "убийств", "похороны", "криминал", "арест", "тюрьм", "суд"
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

def is_safe_text(text: str) -> bool:
    """
    Проверяет текст на наличие слов из черного списка.
    Возвращает True, если текст безопасен.
    """
    if not text:
        return True
    text_lower = text.lower()
    for word in BLACK_LIST_WORDS:
        if word in text_lower:
            return False
    return True

async def fetch_trending_news():
    """
    Fetches trending news from Google News RSS.
    Returns a list of dicts {"title": headline, "description": details}.
    """
    # Перемешиваем URL, чтобы выбирать разные категории
    urls = list(NEWS_URLS)
    random.shuffle(urls)

    news_items = []

    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to fetch news from {url}: {resp.status}")
                        continue

                    text = await resp.text()
                    root = ET.fromstring(text)

                    for item in root.findall(".//item"):
                        title_elem = item.find("title")
                        desc_elem = item.find("description")

                        title = title_elem.text if title_elem is not None else ""
                        description = desc_elem.text if desc_elem is not None else ""

                        # Обычно заголовки имеют формат "Headline - Source"
                        if " - " in title:
                            title = title.rsplit(" - ", 1)[0]

                        cleaned_desc = clean_html(description)

                        # Первичная жесткая фильтрация на уровне бэкенда по стоп-листу
                        if is_safe_text(title) and is_safe_text(cleaned_desc):
                            news_items.append({
                                "title": title,
                                "description": cleaned_desc
                            })
                        else:
                            logger.info(f"🚫 Новость отфильтрована (Blacklist): {title}")

                    # Если мы набрали достаточно безопасных новостей, заканчиваем сбор
                    if len(news_items) >= 15:
                        break
            except Exception as e:
                logger.error(f"Error fetching news from {url}: {e}")
                continue

    # Возвращаем первые 10 новостей
    return news_items[:10]

if __name__ == "__main__":
    import asyncio
    async def test():
        news = await fetch_trending_news()
        print(f"Найдено безопасных новостей: {len(news)}")
        for i, item in enumerate(news[:3]):
            print(f"{i+1}. {item['title']}\n   {item['description'][:100]}...")
    asyncio.run(test())
