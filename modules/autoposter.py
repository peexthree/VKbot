import json
import random
import os
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from modules.bot_init import bot
from ai_service import generate_text
from modules.utils.consts import SKIN_VISUALS, SKIN_DISPLAY_NAMES
from modules.utils.photos import upload_wall_photo
from database.autoposter import get_recent_topics, add_post_history

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

    # 1. Получаем список последних 30 тем (слагов), чтобы избежать повторов
    recent_slugs = await get_recent_topics(limit=30)

    # Собираем все доступные темы
    all_available_topics = []
    for cat, t_list in topics_by_category.items():
        for t in t_list:
            t_slug = t.replace(' ', '_').replace('?', '').replace('!', '')
            if t_slug not in recent_slugs:
                all_available_topics.append((cat, t))

    # Если все темы уже были использованы, берем любую
    if not all_available_topics:
        logger.warning("Все темы из списка уже были опубликованы за последние 30 дней. Сбрасываю фильтр.")
        for cat, t_list in topics_by_category.items():
            for t in t_list:
                all_available_topics.append((cat, t))

    # Выбор случайного персонажа и темы
    skin_id = random.choice(skin_ids)
    category, topic = random.choice(all_available_topics)
    skin_name = SKIN_DISPLAY_NAMES.get(skin_id, skin_id)

    logger.info(f"Генерация поста: персонаж {skin_id}, тема '{topic}'")

    # Формирование промпта.
    prompt = (
        f"Напиши пост на тему: «{topic}» для проекта «Анти-Тар».\n"
        f"Ты — {skin_name}. Начни пост с того, что представишься и скажешь, что тебе сегодня дарована воля написать этот пост.\n"
        f"Используй в посте актуальную новостную повестку (астрологические события недели, громкие научные новости или виральные мемы), "
        f"адаптируй их под свой характер. Сделай интригующее вступление.\n"
        f"Текст должен быть коротким, цепляющим, для стены ВК.\n"
        f"В конце обязательно добавь 5 хэштегов. Первые два: #АнтиТаро #Психология. Остальные три — релевантные теме поста.\n"
        f"НЕ ДОБАВЛЯЙ в генерируемый текст заголовок темы и призывы к действию, я добавлю их сам."
    )

    # Мы передаем skin_id, и generate_text сам возьмет нужный TOV из SKIN_MAP в prompts/personas.py
    ai_text = await generate_text(prompt, skin=skin_id)
    if not ai_text:
        logger.error("Не удалось сгенерировать текст поста")
        return None

    # Формируем финальный текст с архитектурой по заказу
    final_text = (
        f"Ежедневный постинг АНТИ-ТАР\n"
        f"Персонаж: {skin_name}\n"
        f"Тема: «{topic}»\n\n"
        f"{ai_text}\n\n"
        f"Заходи в Зал Пророков Анти-Тар и забери свой первый разбор абсолютно бесплатно: "
        f"https://vk.me/club{GROUP_ID}?ref=autopost_{topic.replace(' ', '_').replace('?', '').replace('!', '')}"
    )

    return {
        "text": final_text,
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

        # Подготовка фото для стены
        photo_filename = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
        attachment = await upload_wall_photo(bot.api, photo_filename)

        # Публикация на Стену сообщества
        res_wall = await bot.api.wall.post(
            owner_id=-GROUP_ID,
            from_group=1,
            message=text,
            attachments=attachment
        )
        logger.info(f"Пост опубликован на стену: {res_wall.post_id}")

        # Записываем в историю публикаций
        topic_slug = post_data["topic"].replace(' ', '_').replace('?', '').replace('!', '')
        await add_post_history(topic_slug)

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
