import json
import random
import os
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from modules.bot_init import bot
from ai_service import generate_text
from modules.utils.consts import SKIN_VISUALS
from modules.utils.photos import upload_local_photo

# Загрузка тем и персонажей
CONTENT_PATH = "data/content_core.json"
GROUP_ID = int(os.environ.get("GROUP_ID", "219181948"))

def load_content():
    with open(CONTENT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def generate_post():
    content = load_content()
    skin_ids = list(content["TONES"].keys())
    topics_by_category = content["TOPICS"]

    # Выбор случайного персонажа и темы
    skin_id = random.choice(skin_ids)
    category = random.choice(list(topics_by_category.keys()))
    topic = random.choice(topics_by_category[category])

    logger.info(f"Генерация поста: персонаж {skin_id}, тема '{topic}'")

    # Формирование промпта. Тон голоса (TOV) добавится автоматически в generate_text
    prompt = (
        f"Напиши пост на тему: «{topic}».\n"
        f"Используй в посте актуальную новостную повестку (астрологические события недели, громкие научные новости или виральные мемы), "
        f"адаптируй их под свой характер. Сделай мощный призыв перейти в бота.\n"
        f"Текст должен быть коротким, цепляющим, для стены ВК.\n"
        f"В конце добавь фиксированный призыв:\n"
        f"Заходи в Зал Пророков и забери свой первый разбор абсолютно бесплатно: "
        f"https://vk.me/club{GROUP_ID}?ref=autopost_{topic.replace(' ', '_').replace('?', '').replace('!', '')}"
    )

    # Мы передаем skin_id, и generate_text сам возьмет нужный TOV из SKIN_MAP в prompts/personas.py
    text = await generate_text(prompt, skin=skin_id)
    if not text:
        logger.error("Не удалось сгенерировать текст поста")
        return None

    return {
        "text": text,
        "skin_id": skin_id,
        "topic": topic,
        "category": category
    }

async def post_to_vk():
    try:
        post_data = await generate_post()
        if not post_data:
            return

        text = post_data["text"]
        skin_id = post_data["skin_id"]

        # Подготовка фото
        photo_filename = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
        attachment = await upload_local_photo(bot.api, photo_filename)

        # 1. Публикация в Канал
        res = await bot.api.wall.post(
            owner_id=-GROUP_ID,
            from_group=1,
            message=text,
            attachments=attachment,
            **{"channel": 1}
        )
        post_id = res.post_id
        logger.info(f"Пост опубликован в канал: {post_id}")

        # 2. Репост на стену сообщества
        repost_msg = "Мы опубликовали новый совет в нашем Канале. Читай первым!"
        await bot.api.wall.repost(
            object=f"wall-{GROUP_ID}_{post_id}",
            message=repost_msg,
            group_id=GROUP_ID
        )
        logger.info(f"Сделан репост записи {post_id} на стену")

    except Exception as e:
        logger.exception(f"Ошибка при автопостинге: {e}")

def setup_autoposter():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # 19:00 MSK ± 15 минут
    hour = 19
    minute = random.randint(0, 30)

    scheduler.add_job(
        post_to_vk,
        CronTrigger(hour=hour, minute=minute),
        name="daily_autopost"
    )

    scheduler.start()
    logger.info(f"Автопостинг настроен на {hour}:{minute:02d} MSK ежедневно")
    return scheduler
