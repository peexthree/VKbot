import json
import random
import os
import datetime
from datetime import timezone, timedelta
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from modules.bot_init import bot
from ai_service import generate_text
from modules.utils.consts import SKIN_VISUALS, SKIN_DISPLAY_NAMES
from modules.utils.photos import upload_wall_photo
from modules.utils.logic import slugify, clean_topic_ref
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
            t_slug = slugify(t)
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

    # Получаем текущую дату и день недели по МСК
    now = datetime.datetime.now(timezone(timedelta(hours=3)))
    days_of_week = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    current_day = days_of_week[now.weekday()]
    current_date_str = now.strftime("%d.%m.%Y")

    # Формирование промпта для полной автономности
    prompt = (
        f"Сегодня {current_date_str}, {current_day}. Напиши полностью готовый к публикации виральный пост для паблика Анти-Тар.\n"
        f"Твоя роль: {skin_name}. Твой тон: мрачный, мистический, хлесткий. Без ванильной психологии. Руби суровую кармическую правду.\n\n"
        f"Базовая тема поста: «{topic}». Тебе нужно раскрыть ее по следующей структуре:\n"
        f"1. Заголовок: Придумай для этой темы провокационный, цепляющий заголовок КАПСОМ.\n\n"
        f"2. Вторжение в реальность: Начни текст с упоминания текущего дня недели ({current_day}) и свяжи его с типичным разрушительным состоянием людей сегодня. Обязательно органично впиши свое имя ({skin_name}) в первую или вторую фразу (например: «Я, баба Ванга, вижу...» или «Олеся Ивонченко наблюдает за вами...»). Сделай вид, что стоишь у них за спиной.\n\n"
        f"3. Вскрытие боли: Резко перейди к сути темы «{topic}». Не читай лекций — вскрывай раны. Покажи, как люди сами ломают свою судьбу.\n\n"
        f"4. Запретное знание: Выдай одно жесткое эзотерическое правило по этой теме как непреложный закон Вселенной.\n\n"
        f"5. Вовлечение: Закончи пост одним неудобным вопросом, который заденет гордость читателя и вынудит спорить в комментариях.\n\n"
        f"Технические требования:\n"
        f"- Текст должен быть коротким, информативным и бить точно в цель.\n"
        f"- В самом конце текста с новой строки добавь 5 хэштегов (первые два обязательны: #АнтиТаро #Психология).\n"
        f"- НЕ пиши никаких призывов переходить по ссылкам (это сделает система).\n"
        f"- НЕ выводи техническую информацию, отвечай только готовым текстом поста."
    )

    # Мы передаем skin_id, и generate_text сам возьмет нужный TOV из SKIN_MAP в prompts/personas.py
    ai_text = await generate_text(prompt, skin=skin_id)
    if not ai_text:
        logger.error("Не удалось сгенерировать текст поста")
        return None

    # Формируем финальный текст для СТЕНЫ (чистый текст от ИИ + ссылка)
    topic_ref = clean_topic_ref(topic)
    final_text = (
        f"{ai_text}\n\n"
        f"Заходи в Зал Пророков Анти-Тар и забери свой первый разбор абсолютно бесплатно: "
        f"https://vk.me/club{GROUP_ID}?ref=autopost_{topic_ref}"
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

        if not attachment:
            logger.error(f"Аборт публикации: не удалось загрузить фото {photo_filename}")
            return

        # Публикация на Стену сообщества
        res_wall = await bot.api.wall.post(
            owner_id=-GROUP_ID,
            from_group=1,
            message=text,
            attachments=attachment
        )
        logger.info(f"Пост опубликован на стену: {res_wall.post_id}")

        # Записываем в историю публикаций
        topic_slug = slugify(post_data["topic"])
        await add_post_history(topic_slug)

    except Exception as e:
        logger.exception(f"Ошибка при автопостинге: {e}")

def setup_autoposter():
    scheduler = AsyncIOScheduler(timezone="UTC")

    # 10:00 UTC + 0..30 минут
    hour = 10
    minute = random.randint(0, 30)

    scheduler.add_job(
        post_to_vk,
        CronTrigger(hour=hour, minute=minute),
        name="daily_autopost"
    )

    scheduler.start()
    logger.info(f"Автопостинг настроен на {hour}:{minute:02d} UTC ежедневно")
    return scheduler
