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
from modules.utils.consts import SKIN_VISUALS, SKIN_DISPLAY_NAMES, SKIN_SHORT_NAMES, SKIN_EMOJIS
from modules.utils.photos import upload_wall_photo

# Загрузка тем и персонажей
CONTENT_PATH = "data/content_core.json"
GROUP_ID = int(os.environ.get("GROUP_ID", "219181948"))

def load_content():
    with open(CONTENT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def generate_post(is_morning: bool = True):
    content = load_content()
    skin_ids = list(content["TONES"].keys())
    topics_by_category = content["TOPICS"]

    # 1. Получаем список недавно использованного контента за 24ч
    from database.autoposter import get_daily_used_content, get_active_poll, close_poll
    used_skins, used_topics = await get_daily_used_content()

    # 2. Проверка активного опроса (результаты вчерашнего голосования)
    forced_topic = None
    active_poll = await get_active_poll()
    if active_poll:
        try:
            # Вытягиваем данные опроса из ВК (метод getById возвращает список)
            res = await bot.api.request("polls.getById", {
                "owner_id": active_poll["owner_id"],
                "poll_id": active_poll["poll_id"]
            })
            if res and isinstance(res, list) and len(res) > 0:
                poll_data = res[0]
                if poll_data.get("answers"):
                    # Определяем вариант с максимальным количеством голосов
                    winner = max(poll_data["answers"], key=lambda a: a.get("votes", 0))
                    forced_topic = winner.get("text")
                    logger.info(f"Тема выбрана пользователями через опрос: {forced_topic}")
        except Exception as e:
            logger.error(f"Не удалось получить результаты опроса: {e}")
            forced_topic = active_poll["topic_name"]

        await close_poll(active_poll["id"])

    # Собираем все доступные темы
    all_available_topics = []
    for cat, t_list in topics_by_category.items():
        for t in t_list:
            if t not in used_topics:
                all_available_topics.append((cat, t))

    if forced_topic:
        category = "Голосование"
        topic = forced_topic
    elif all_available_topics:
        category, topic = random.choice(all_available_topics)
    else:
        category, topic = random.choice([(c, t) for c, ts in topics_by_category.items() for t in ts])

    # Выбор персонажа (исключая использованных за 24ч)
    available_skins = [s for s in skin_ids if s not in used_skins]
    if not available_skins:
        available_skins = skin_ids

    skin_id = random.choice(available_skins)
    skin_name = SKIN_DISPLAY_NAMES.get(skin_id, skin_id)

    # Выбор рубрики и тона
    if is_morning:
        rubrics = ["PROVOCATION", "MYTH_BUST", "BATTLE", "PRACTICUM"]
        tones = ["Жесткий цинизм", "Дерзкая провокация"]
    else:
        rubrics = ["SUPPORT", "FACT", "POLL"]
        tones = ["Психологическое сочувствие", "Глубокий экспертный инсайт"]

    rubric = random.choice(rubrics)
    tone = random.choice(tones)

    # Логика Битвы Архетипов
    opponent_id = ""
    opponent_name = ""
    if rubric == "BATTLE":
        opponents = [s for s in skin_ids if s != skin_id]
        opponent_id = random.choice(opponents)
        opponent_name = SKIN_DISPLAY_NAMES.get(opponent_id, opponent_id)

    logger.info(f"Генерация поста: {rubric}, персонаж {skin_id}, тема '{topic}'")

    # Получаем текущую дату по UTC+5 (Башкирия)
    tz_bash = timezone(timedelta(hours=5))
    now = datetime.datetime.now(tz_bash)
    days_of_week = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    current_day = days_of_week[now.weekday()]
    current_date_str = now.strftime("%d.%m.%Y")

    # Формирование специфических инструкций под рубрику
    rubric_instructions = {
        "PROVOCATION": (
            "Это ультра-короткий пост-провокация (3-4 предложения). "
            "Задай один крайне неудобный и хлесткий вопрос в лоб, который заставит читателя чувствовать дискомфорт от своей пассивности. "
            "Никаких советов и практикумов. Только удар по гордости и призыв в бота."
        ),
        "MYTH_BUST": (
            "Разрушение мифов. Возьми популярное заблуждение в эзотерике (ретроградный меркурий, марафоны желаний, денежные аффирмации) "
            "и жестко разнеси его с позиции приземленной психологии и твоего персонажа. Покажи, почему это ловушка для дураков."
        ),
        "BATTLE": (
            f"Битва Архетипов. Это диалог-стычка между тобой ({skin_name}) и персонажем {opponent_name}. "
            f"Вы спорите на тему «{topic}». Ты гнешь свою линию, {opponent_name} — свою. "
            "Диалог должен быть динамичным, острым и коротким. Каждая реплика должна начинаться с новой строки в формате:\n"
            f"{SKIN_EMOJIS.get(skin_id, '👁')} {SKIN_SHORT_NAMES.get(skin_id, skin_id)}: Текст реплики...\n"
            f"{SKIN_EMOJIS.get(opponent_id, '👁')} {SKIN_SHORT_NAMES.get(opponent_id, opponent_id)}: Текст реплики...\n"
            "В конце диалога обязательно добавь свой финальный едкий вывод без префикса имени."
        ),
        "PRACTICUM": (
            "Классический жесткий практикум. Вскрой боль темы и дай 3 конкретных шага (дефисы), как сломать старый сценарий завтра."
        ),
        "SUPPORT": (
            "Сакральная поддержка. В этом посте ты не ругаешь, а глубоко сочувствуешь боли читателя. "
            "Скажи, что быть не в порядке — это нормально. Дай мягкий, обволакивающий совет, как трансформировать эту боль в ресурс."
        ),
        "FACT": (
            "Мистический факт. Расскажи удивительный, малоизвестный факт из истории мистики, хиромантии или психологии Юнга, "
            "связанный с темой поста. Подача должна быть авторитетной и глубокой."
        ),
        "POLL": (
            "Интерактивный опрос. Напиши интригующее вступление к теме, подведи к тому, что выбор за читателем. "
            "Текст должен обрываться на вопросе, на который люди ответят в опросе ниже."
        )
    }

    prompt = (
        f"Текущая дата: {current_date_str}, день недели: {current_day}. "
        "Напиши виральный пост для паблика Анти-Тар.\n"
        f"Твоя роль: {skin_name}. Твой эмоциональный тон: {tone}.\n"
        f"Рубрика поста: {rubric}. Инструкция: {rubric_instructions.get(rubric)}\n\n"
        f"Базовая тема: «{topic}».\n\n"
        "Технические требования:\n"
        "- Используй ЭМОДЗИ СТРОГО как маркеры персонажей в начале реплик (для Битвы) или как редкие акценты (не более 3-5 на весь пост).\n"
        "- РАЗРЕШЕНО использовать КАПС для имен персонажей в Битве и для 2-3 важных слов-триггеров в тексте.\n"
        "- Текст должен быть нативным, без приветствий и лишней воды.\n"
        "- В конце текста добавь нативный призыв нажать кнопку «Написать сообществу» под постом (каждый раз формулируй по-разному в своем стиле).\n"
        "- СРАЗУ ПОСЛЕ ПРИЗЫВА, самой последней строкой, выведи 5 хэштегов: #АнтиТар #Психология + 3 по теме.\n"
        "- НИКАКИХ внешних ссылок!"
    )

    # Мы передаем skin_id, и generate_text сам возьмет нужный TOV из SKIN_MAP в prompts/personas.py
    ai_text = await generate_text(prompt, skin=skin_id)
    if not ai_text:
        logger.error("Не удалось сгенерировать текст поста")
        return None

    # Агрессивный предохранитель хэштегов: обрабатываем именно ai_text
    ai_lines = [line.strip() for line in ai_text.strip().split('\n') if line.strip()]
    if ai_lines:
        # Ищем строку с хэштегами (обычно последняя или предпоследняя)
        tag_line_index = -1
        for i in range(len(ai_lines) - 1, max(-1, len(ai_lines) - 3), -1):
            words = ai_lines[i].split()
            # Если в строке 3-10 слов и она последняя ИЛИ содержит # ИЛИ длинные слова (теги)
            if 3 <= len(words) <= 10:
                if i == len(ai_lines) - 1 or any(w.startswith('#') or len(w) > 10 for w in words):
                    tag_line_index = i
                    break

        if tag_line_index != -1:
            words = ai_lines[tag_line_index].split()
            fixed_tags = [f"#{word.lstrip('#').rstrip('.,!?;')}" for word in words]
            ai_lines[tag_line_index] = " ".join(fixed_tags)

            # Если теги не в самом конце - переносим их в конец
            if tag_line_index != len(ai_lines) - 1:
                tags = ai_lines.pop(tag_line_index)
                ai_lines.append(tags)

        ai_text = "\n\n".join(ai_lines)

    # Нативный текст без ссылок
    final_text = ai_text.strip()

    return {
        "text": final_text,
        "skin_id": skin_id,
        "opponent_id": opponent_id,
        "topic": topic,
        "category": category,
        "rubric": rubric
    }

async def create_vk_poll(options: list):
    """Создает опрос в ВК с выбором тем на завтра"""
    try:
        poll = await bot.api.polls.create(
            question="Какую зону твоей Матрицы вскрыть завтра?",
            add_answers=json.dumps(options, ensure_ascii=False),
            owner_id=-GROUP_ID
        )
        return poll
    except Exception as e:
        logger.error(f"Ошибка при создании опроса: {e}")
    return None

async def post_to_vk(is_morning: bool = True):
    try:
        post_data = await generate_post(is_morning=is_morning)
        if not post_data:
            return

        text = post_data["text"]
        skin_id = post_data["skin_id"]
        opponent_id = post_data.get("opponent_id")
        rubric = post_data["rubric"]
        topic = post_data["topic"]

        # Подготовка вложений (Фото персонажа или Карта Таро)
        attachments = []

        if rubric == "BATTLE" and opponent_id:
            # Для Битвы - всегда два персонажа
            photo1 = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
            photo2 = SKIN_VISUALS.get(opponent_id, "main_menu.jpeg")

            att1 = await upload_wall_photo(bot.api, photo1)
            att2 = await upload_wall_photo(bot.api, photo2)

            if att1: attachments.append(att1)
            if att2: attachments.append(att2)
        else:
            # Основное фото персонажа
            photo_filename = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
            att = await upload_wall_photo(bot.api, photo_filename)
            if att:
                attachments.append(att)

            # Шанс 20% на карту Таро в дополнение (карусель)
            if random.random() < 0.2 and rubric != "POLL":
                card_id = random.randint(0, 77)
                card_filename = f"cards/{card_id}.jpeg"
                logger.info(f"Выбрана доп. карта Таро для поста: {card_filename}")
                att_card = await upload_wall_photo(bot.api, card_filename)
                if att_card:
                    attachments.append(att_card)

        # Если рубрика POLL - создаем и крепим опрос с вариантами тем на завтра
        if rubric == "POLL":
            # Выбираем 3 случайные темы для голосования
            content = load_content()
            all_topics = [t for ts in content["TOPICS"].values() for t in ts]
            poll_options = random.sample(all_topics, min(4, len(all_topics)))

            poll = await create_vk_poll(poll_options)
            if poll:
                attachments.append(f"poll{poll.owner_id}_{poll.id}")
                # Сохраняем опрос в БД для завтрашнего анализа
                from database.autoposter import save_active_poll
                await save_active_poll(poll.id, poll.owner_id, "Голосование", poll_options)

        if not attachments:
            logger.error("Аборт публикации: нет вложений")
            return

        # Публикация на Стену сообщества
        res_wall = await bot.api.wall.post(
            owner_id=-GROUP_ID,
            from_group=1,
            message=text,
            attachments=",".join(attachments)
        )
        logger.info(f"Пост опубликован на стену: {res_wall.post_id}")

        # Записываем в историю публикаций (используем и тему и скин для лога 24ч)
        from database.autoposter import add_post_history
        await add_post_history(topic, skin_id=skin_id)

    except Exception as e:
        logger.exception(f"Ошибка при автопостинге: {e}")

def setup_autoposter():
    # Таймзона Башкортостана (UTC+5)
    bash_tz = "Asia/Yekaterinburg"
    scheduler = AsyncIOScheduler(timezone=bash_tz)

    # 🌅 Утренний выход: 08:00 - 09:00
    morning_hour = 8
    morning_minute = random.randint(0, 59)

    # 🌌 Вечерний выход: 19:00 - 21:00
    evening_hour = random.randint(19, 20)
    evening_minute = random.randint(0, 59)

    # Утреннее задание
    scheduler.add_job(
        post_to_vk,
        CronTrigger(hour=morning_hour, minute=morning_minute),
        kwargs={"is_morning": True},
        name="morning_autopost"
    )

    # Вечернее задание
    scheduler.add_job(
        post_to_vk,
        CronTrigger(hour=evening_hour, minute=evening_minute),
        kwargs={"is_morning": False},
        name="evening_autopost"
    )

    scheduler.start()
    logger.info(f"Автопостинг настроен (UTC+5): Утро {morning_hour}:{morning_minute:02d}, Вечер {evening_hour}:{evening_minute:02d}")
    return scheduler
