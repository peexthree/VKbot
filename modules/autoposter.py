import json
import random
import os
import datetime
from datetime import timezone, timedelta
from loguru import logger
from os.path import exists
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from vkbottle.bot import BotLabeler
from vkbottle import GroupEventType
import re

from modules.bot_init import bot
from ai_service import generate_text, clean_ai_json, sanitize_user_input
from prompts.rubrics import RUBRIC_PROMPTS
from cache import redis_client as redis
from database.autoposter import (
    get_daily_used_content, get_active_poll, close_poll,
    save_hidden_promo, get_least_recent_rubric, save_active_poll,
    add_post_history
)
from database import get_user
from modules.utils.logic import (
    extract_russian_date, calculate_destiny_card, calculate_purpose_arcana,
    calculate_user_rank
)
from modules.utils.visual import generate_diagnosis_card, generate_card_history_image
from modules.utils.consts import (
    SKIN_VISUALS, SKIN_DISPLAY_NAMES, SKIN_SHORT_NAMES,
    SKIN_EMOJIS, HIDDEN_CIPHER_WORDS, ADMIN_ID
)
from modules.utils.photos import upload_wall_photo
from modules.utils.news import fetch_trending_news
from cards_data import get_card_data

# Загрузка тем и персонажей
CONTENT_PATH = "data/content_core.json"
GROUP_ID = int(os.environ.get("GROUP_ID", "219181948"))

RUBRIC_NAMES = {
    "PROVOCATION": "ПРОВОКАЦИЯ",
    "MYTH_BUST": "РАЗРУШЕНИЕ МИФОВ",
    "BATTLE": "БИТВА АРХЕТИПОВ",
    "PRACTICUM": "ПРАКТИКУМ",
    "SUPPORT": "САКРАЛЬНАЯ ПОДДЕРЖКА",
    "FACT": "МИСТИЧЕСКИЙ ФАКТ",
    "POLL": "ИНТЕРАКТИВНЫЙ ОПРОС",
    "NEWS_BREAKDOWN": "РАЗБОР ИНФОПОВОДА",
    "STAR_SYNASTRY": "ЗВЕЗДНЫЙ РАЗБОР",
    "TREND_WATCH": "ТРЕНД-АНАЛИЗ",
    "CARD_HISTORY": "ИСТОРИЯ АРКАНА",
    "SACRED_SCIENCE": "САКРАЛЬНАЯ НАУКА",
    "DREAM_DECODING": "ХРОНИКИ СНОВ",
    "PALM_CHRONICLES": "ТАЙНЫ ХИРОМАНТИИ",
    "KARMA_STORY": "КАРМИЧЕСКАЯ ХРОНИКА",
    "CHAKRA_FLOW": "ПОТОКИ ЧАКР",
    "SACRED_RITUAL": "САКРАЛЬНЫЙ РИТУАЛ"
}

labeler = BotLabeler()

# ==================== САКРАЛЬНЫЙ ПУЛ И ЦИКЛИЧЕСКАЯ ОЧЕРЕДЬ ====================

async def get_remaining_rubrics_pool() -> list:
    """Возвращает список оставшихся рубрик в текущем цикле из Redis."""
    try:
        val = await redis.get("autopost_pool:remaining")
        if val:
            decoded = val.decode() if isinstance(val, bytes) else val
            pool = json.loads(decoded)
            if isinstance(pool, list) and pool:
                valid_pool = [r for r in pool if r in RUBRIC_NAMES]
                if valid_pool:
                    return valid_pool
    except Exception as e:
        logger.error(f"Ошибка получения пула рубрик из Redis: {e}")

    return await reset_rubrics_pool()

async def reset_rubrics_pool() -> list:
    """Инициализирует/сбрасывает пул всеми 17 рубриками."""
    pool = list(RUBRIC_NAMES.keys())
    try:
        await redis.set("autopost_pool:remaining", json.dumps(pool))
        logger.info(f"🔄 Сакральный круг замкнулся. Пул рубрик инициализирован заново: {pool}")
    except Exception as e:
        logger.error(f"Ошибка сохранения пула рубрик в Redis: {e}")
    return pool

async def save_rubrics_pool(pool: list):
    """Сохраняет текущий пул рубрик в Redis."""
    try:
        await redis.set("autopost_pool:remaining", json.dumps(pool))
    except Exception as e:
        logger.error(f"Ошибка сохранения пула рубрик в Redis: {e}")

async def pull_next_rubric() -> str:
    """Берет случайную рубрику из оставшихся в пуле и удаляет ее."""
    pool = await get_remaining_rubrics_pool()
    if not pool:
        pool = await reset_rubrics_pool()

    rubric = random.choice(pool)
    pool.remove(rubric)
    await save_rubrics_pool(pool)
    logger.info(f"🔮 Из пула выбрана рубрика: {rubric}. Осталось в пуле: {len(pool)} рубрик.")
    return rubric

async def draw_fallback_rubric(failed_rubric: str) -> str:
    """
    Если выбранная новостная рубрика дала сбой, возвращаем её обратно в пул
    и выбираем любую другую доступную рубрику.
    """
    pool = await get_remaining_rubrics_pool()
    if failed_rubric not in pool:
        pool.append(failed_rubric)

    alternatives = [r for r in pool if r != failed_rubric]
    if not alternatives:
        await reset_rubrics_pool()
        pool = await get_remaining_rubrics_pool()
        alternatives = [r for r in pool if r != failed_rubric]
        if not alternatives:
            alternatives = pool

    chosen = random.choice(alternatives)
    if chosen in pool:
        pool.remove(chosen)
    await save_rubrics_pool(pool)
    logger.warning(f"⚠️ Фолбэк: вместо зафейленной {failed_rubric} выбрана {chosen}. Пул сохранен.")
    return chosen

# ==============================================================================

@labeler.raw_event(GroupEventType.WALL_POST_NEW, dataclass=dict)
async def ignore_self_wall_posts(event: dict):
    """
    Защита от самопостинга: игнорируем события о новых постах,
    если они созданы самим сообществом.
    """
    obj = event.get("object", {})
    try:
        from_id = int(obj.get("from_id", 0))
    except (ValueError, TypeError):
        from_id = 0

    if from_id == -GROUP_ID:
        return

@labeler.raw_event(GroupEventType.WALL_REPLY_NEW, dataclass=dict)
async def handle_diagnosis_comment(event: dict):
    """
    Интерактив «Вскрытие»: ответ на комментарий с датой рождения.
    """
    obj = event.get("object", {})
    text = obj.get("text", "")
    try:
        from_id = int(obj.get("from_id", 0))
        post_id = int(obj.get("post_id", 0))
        comment_id = int(obj.get("id", 0))
    except (ValueError, TypeError):
        return

    if from_id <= 0: return # Игнорируем группы и пустые ID

    birth_date = extract_russian_date(text)

    # Проверка, что дата является основой сообщения (не слишком длинный текст и дата присутствует)
    if birth_date and len(text.strip()) < 50:
        s_text = sanitize_user_input(text)
        logger.info(f"Получен запрос на вскрытие от {from_id} под постом {post_id}: {birth_date}")

        # Получаем имя пользователя из ВК
        try:
            vk_users = await bot.api.users.get(user_ids=[from_id])
            user_name = vk_users[0].first_name if vk_users else "Адепт"
        except Exception:
            user_name = "Адепт"

        # ПОЛУЧЕНИЕ ПРИВЯЗАННОГО ПЕРСОНАЖА ИЗ REDIS
        try:
            target_skin = await redis.get(f"post_skin:{post_id}")
            if target_skin:
                target_skin = target_skin.decode() if isinstance(target_skin, bytes) else target_skin
                logger.info(f"Для поста {post_id} найден привязанный персонаж: {target_skin}")
            else:
                target_skin = random.choice(list(SKIN_DISPLAY_NAMES.keys()))
                logger.info(f"Персонаж для поста {post_id} не найден в кэше, выбран рандомный: {target_skin}")
        except Exception as e:
            logger.error(f"Ошибка получения скина из Redis: {e}")
            target_skin = "olesya"

        main_arcana = calculate_destiny_card(birth_date)
        purpose_arcana = calculate_purpose_arcana(birth_date)

        user = await get_user(from_id)

        if user:
            level, _ = calculate_user_rank(user)
            active_skin_id = user.get("active_skin", "olesya")
            active_skin_name = SKIN_DISPLAY_NAMES.get(active_skin_id, active_skin_id)

            user_context = (
                f"Адепт: {user_name}, Уровень: {level}, Активный персонаж: {active_skin_name}. "
                f"Главный Аркан Судьбы: {main_arcana}, Аркан Предназначения: {purpose_arcana}."
            )
        else:
            user_context = (
                f"Адепт: {user_name} (не зарегистрирован). "
                f"Главный Аркан Судьбы: {main_arcana}, Аркан Предназначения: {purpose_arcana}."
            )

        prompt = (
            f"Проведи мгновенное нумерологический разбор («Откровение») адепта на основе его Арканов: {user_context}. "
            f"Пользователь также написал: <user_input>{s_text}</user_input>. "
            f"Твой ответ должен быть максимально ядовитым, жестким и психологически точным «диагнозом» его текущего состояния. "
            f"Бей по теневым сторонам именно этих Арканов ({main_arcana} и {purpose_arcana}). "
            "Помни: инструменты (цифры, арканы) безупречны, проблема всегда в кармических блоках и лени самого пользователя. "
            "Используй стиль Анти-Таро: цинизм, никакой пощады, метафоры звездной карты и кармических узлов. "
            f"ОБЯЗАТЕЛЬНО упомяни цифры Арканов ({main_arcana} и {purpose_arcana}) в тексте разбора. "
            "Объем: 2-3 хлестких предложения. Без приветствий."
        )

        diagnosis = await generate_text(prompt, skin=target_skin, is_background=True)
        if diagnosis and diagnosis != "ERROR_RPM_LIMIT":
            # Принудительная очистка
            diagnosis = diagnosis.replace("\\n", "\n").replace("—", "-").replace("*", "")

            final_message = f"[id{from_id}|{user_name}], {diagnosis}"

            if not user:
                cta = "\n\nЭто лишь малая искра твоего истинного величия. Чтобы получить полный сакральный разбор, сонастроить жизненные потоки и забрать путеводитель по судьбе, нажми кнопку \"Написать сообществу\" и отправь команду \"Старт\"."
                final_message += cta

            try:
                await bot.api.wall.create_comment(
                    owner_id=-GROUP_ID,
                    post_id=post_id,
                    reply_to_comment=comment_id,
                    message=final_message
                )
            except Exception as e:
                logger.error(f"Ошибка при ответе на комментарий: {e}")

def load_content():
    with open(CONTENT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def generate_post(is_morning: bool = True, forced_rubric: str = None):
    content = load_content()
    skin_ids = list(content["TONES"].keys())
    topics_by_category = content["TOPICS"]
    news_context = ""

    # 1. Получаем список недавно использованного контента за 72ч
    used_skins, used_topics, used_rubrics = await get_daily_used_content()

    # 2. Проверка активного опроса (результаты вчерашнего голосования)
    forced_topic = None
    active_poll = await get_active_poll()
    if active_poll:
        try:
            res = await bot.api.request("polls.getById", {
                "owner_id": active_poll["owner_id"],
                "poll_id": active_poll["poll_id"]
            })
            if res and isinstance(res, list) and len(res) > 0:
                poll_data = res[0]
                if poll_data.get("answers"):
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

    # Выбор рубрики
    if forced_rubric:
        rubric = forced_rubric
    else:
        rubric = await pull_next_rubric()

    # Обработка новостных рубрик и фолбэк
    if rubric in ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"]:
        news_list = await fetch_trending_news()
        if not news_list:
            logger.warning(f"⚠️ Не удалось получить новости для {rubric}, выполняем фолбэк...")
            rubric = await draw_fallback_rubric(rubric)
            if rubric in ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"]:
                # Если выбранная на замену рубрика тоже новостная, пробуем стянуть новости еще раз
                news_list = await fetch_trending_news()
                if not news_list:
                    # Сверхжесткий фолбэк на гарантированно не-новостную из оставшихся или просто случайную
                    pool = await get_remaining_rubrics_pool()
                    non_news = [r for r in pool if r not in ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"]]
                    if not non_news:
                        non_news = [r for r in RUBRIC_NAMES.keys() if r not in ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"]]
                    rubric = random.choice(non_news)
                    logger.warning(f"⚠️ Сверхжесткий фолбэк на ненавостную рубрику: {rubric}")

        if rubric in ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"] and news_list:
            selected_news = news_list[:4]
            topic = selected_news[0]["title"]
            news_context = "\n".join([f"НОВОСТЬ {i+1}: {n['title']}\nФАКТУРА: {n['description']}" for i, n in enumerate(selected_news)])
            category = "Новости"
            tones = ["Эмоциональный разбор", "Высоковибрационный хайп", "Циничный инсайд"]
        else:
            if rubric in ["SUPPORT", "FACT", "POLL", "CARD_HISTORY", "SACRED_SCIENCE", "DREAM_DECODING", "PALM_CHRONICLES", "KARMA_STORY", "CHAKRA_FLOW", "SACRED_RITUAL"]:
                tones = ["Психологическое сочувствие", "Глубокий экспертный инсайт"]
            else:
                tones = ["Жесткий цинизм", "Дерзкая провокация"]
    else:
        if rubric in ["SUPPORT", "FACT", "POLL", "CARD_HISTORY", "SACRED_SCIENCE", "DREAM_DECODING", "PALM_CHRONICLES", "KARMA_STORY", "CHAKRA_FLOW", "SACRED_RITUAL"]:
            tones = ["Психологическое сочувствие", "Глубокий экспертный инсайт"]
        else:
            tones = ["Жесткий цинизм", "Дерзкая провокация"]

    tone = random.choice(tones)

    # Инициализация параметров для CARD_HISTORY
    card_id = None
    card_name = None
    if rubric == "CARD_HISTORY":
        card_id = random.randint(0, 77)
        card_data = get_card_data(card_id)
        card_name = card_data.get("name", "Шут")
        category = "Карты Таро"
        topic = f"История Аркана {card_name}"
        logger.info(f"Выбран случайный Аркан для CARD_HISTORY: {card_name} (ID: {card_id})")

    # СЕТКА ЭЗОТЕРИЧЕСКИХ ДИАГНОЗОВ (ВЕКТОРЫ А, Б, В, Г)
    # Случайный выбор гарантирует 25% вероятность для каждого вектора, включая Вектор Г (Фантазии)
    vector_choice = random.choice(["A", "B", "C", "D"])
    vector_descriptions = {
        "A": "Вектор А (Хаос): Человек делает слишком много пустых, суетливых действий, сливая энергию космоса на ментальный шум вместо точечного удара.",
        "B": "Вектор Б (Страх силы): Человек готов действовать, но блокирует свой потенциал, потому что боится масштаба собственной личности и ответственности перед своей судьбой.",
        "C": "Вектор В (Застой интеллекта): Человек ушел в глухой ментальный анализ, пытается все просчитать головой и полностью заглушил голос вселенной и интуиции.",
        "D": "Вектор Г (Фантазии): Человек уходит в пустые медитации, иллюзии, мечтания и пассивные ожидания чуда без реальных действий."
    }
    vector_instruction = (
        f"КРИТИЧЕСКОЕ ТРЕБОВАНИЕ К ПСИХОЛОГИЧЕСКОМУ АНАЛИЗУ:\n"
        f"В этом посте ты обязан препарировать деструктивное поведение читателя строго через призму следующего вектора:\n"
        f"{vector_descriptions[vector_choice]}\n"
        f"СТРОЖАЙШЕ ЗАПРЕЩЕНО сводить проблему к банальной лени, ленивости или прокрастинации. "
        f"Покажи глубокое понимание этого деструктивного вектора и дай его детальный разбор в ToV нашего проекта."
    )

    # ГЕНЕРАЦИЯ СКРЫТОГО ШИФРА (20% шанс)
    has_promo = random.random() < 0.2
    hidden_code = None
    cipher_instruction = ""
    if has_promo:
        cipher_base = random.choice(HIDDEN_CIPHER_WORDS)
        cipher_num = random.randint(100, 999)
        hidden_code = f"{cipher_base}-{cipher_num}"
        energy_reward = random.randint(50, 200)

        # Сохраняем код в БД
        await save_hidden_promo(hidden_code, energy_reward)
        logger.info(f"Сгенерирован скрытый шифр для поста: {hidden_code} на {energy_reward} ✨")

        cipher_masks = [
            f"как кармический узел или блок (например: 'энергия заблокирована в {hidden_code}')",
            f"как сакральный номер в реестре судеб (например: 'твой индекс в звездной карте - {hidden_code}')",
            f"как мистическую частоту или код доступа (например: 'ключ к переходу - {hidden_code}')",
            f"как количество накопленных грехов или очков кармы (например: 'счетчик тени замер на {hidden_code}')",
            f"как зашифрованное время или координату (например: 'встречаемся в точке {hidden_code}')",
            f"как индекс уровня хайпа или аномалии (например: 'уровень шума в эфире - {hidden_code}')",
            f"как номер старого архивного дела (например: 'согласно протоколу {hidden_code}')"
        ]
        chosen_mask = random.choice(cipher_masks)

        cipher_instruction = (
            f"КРИТИЧЕСКОЕ ЗАДАНИЕ: Вшей в текст поста скрытый игровой шифр: {hidden_code}. "
            f"Подай его как конкретный маркер искажения частоты или кармический узел в звездной карте судьбы читателя. "
            f"Вплети его {chosen_mask}. "
            "Инструкция по интеграции: НЕ выплевывай его сухим текстом в конце или в начале. "
            f"Органично вплети его в сакральное повествование, чтобы он выглядел как естественная часть фразы "
            f"или тайное знание (например: «...тот самый шифр {hidden_code}, открывающий врата...» или «...искажение на частоте {hidden_code}...»). "
            "Он НЕ должен быть в конце или начале. Он должен быть органично вшит в середину одного из абзацев. "
            "Код должен быть написан именно так: КАПСОМ, латиницей, через дефис. "
            "НЕ делай на нем акцент, он должен выглядеть как естественная часть повествования."
        )
    else:
        cipher_instruction = "Скрытый игровой шифр в этом посте использовать НЕ нужно. Не упоминай никакие коды или шифры."

    # Логика Битвы Архетипов
    opponent_id = ""
    opponent_name = ""
    if rubric == "BATTLE":
        opponents = [s for s in skin_ids if s != skin_id]
        opponent_id = random.choice(opponents)
        opponent_name = SKIN_DISPLAY_NAMES.get(opponent_id, opponent_id)

    logger.info(f"Генерация поста: {rubric}, персонаж {skin_id}, tema '{topic}'")

    # Получаем текущую дату по UTC+5 (Башкирия)
    tz_bash = timezone(timedelta(hours=5))
    now = datetime.datetime.now(tz_bash)
    days_of_week = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    current_day = days_of_week[now.weekday()]
    current_date_str = now.strftime("%d.%m.%Y")

    # Рандомизация структуры для борьбы с «одной схемой»
    jitter_caps = random.choice(["используй КАПС для акцентов на 3-5 ключевых словах", "используй КАПС только для финального вывода", "используй КАПС для выделения системных терминов"])

    # Формирование специфических инструкций под рубрику
    rubric_instruction = RUBRIC_PROMPTS.get(rubric, "")
    if rubric == "BATTLE":
        rubric_instruction = rubric_instruction.replace("твоим оппонентом", opponent_name)
    elif rubric in ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"]:
        rubric_instruction = f"СВОДКА НОВОСТЕЙ ДЛЯ РАЗБОРА:\n{news_context}\n\n" + rubric_instruction
    elif rubric == "CARD_HISTORY":
        rubric_instruction = f"ВЫПУСК ПОСВЯЩЕН АРКАНУ: {card_name} (ID/номер {card_id}).\n\n" + rubric_instruction

    is_sunday = False

    # Инструкция по динамической концовке (CTA)
    dynamic_cta_instruction = (
        "КРИТИЧЕСКОЕ ТРЕБОВАНИЕ ДЛЯ КОНЦОВКИ (СТРОГО СОБЛЮДАТЬ): "
        "В самый конец поста (но перед хэштегами) сгенерируй динамический, уникальный, хлесткий и циничный призыв к действию (CTA). "
        "Он должен идеально подстраиваться под текущую тему разбора и твоего персонажа. "
        "Объем этого CTA: строго 2-3 предложения. Текст должен быть максимально спрессованным, "
        "плотным, циничным и глубоким в ToV «Анти-Тар». Никакой банальщины и унылого копипаста. "
        "Запрещено предлагать переслать пост кому-либо. Призыв должен мотивировать читателя зайти в бота."
    )

    prompt_base = (
        f"Текущая дата: {current_date_str}, день недели: {current_day}. "
        "Напиши виральный пост для паблика Анти-Тар. "
        "Твой текст должен стать объемным, плотным и развернутым лонгридом (ОТ 1500 ДО 2500 СИМВОЛОВ). "
        "Никаких коротких отписок и лозунгов. Пиши емко, с конкретными жизненными примерами, "
        "метафорами и глубоким пониманием психологии.\n\n"
        f"Твой роль: {skin_name}. Твой эмоциональный тон: {tone}.\n"
        f"Рубрика поста: {rubric}. ИНСТРУКЦИЯ К РУБРИКЕ: {rubric_instruction}\n\n"
        f"{vector_instruction}\n\n"
        f"{cipher_instruction}\n\n"
        f"{dynamic_cta_instruction}\n\n"
        "ГЛОБАЛЬНАЯ КОМПОЗИЦИЯ: Органично склей четыре элемента: Личность персонажа + Тематику рубрики + Боль/Эго читателя + Уникальный динамический CTA. "
        "Текст должен быть живым, сплошным, с резкими переходами, БЕЗ ПРИВЕТСТВИЙ и лишней воды. "
        "ВАЖНОЕ ТЕХНИЧЕСКОЕ ТРЕБОВАНИЕ: Верни ответ СТРОГО в формате JSON:\n"
        "{\n"
        "  \"text\": \"полный текст поста со всеми призывами и хэштегами\",\n"
        "  \"quote\": \"самая хлесткая и ядовитая фраза из текста для картинки (до 120 символов)\"\n"
        "}"
    )

    if rubric in ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"]:
        prompt = (
            f"{prompt_base}\n\n"
            "Дополнительные требования:\n"
            "- Используй ЭМОДЗИ для создания атмосферы (но не перебарщивай, 5-8 на пост).\n"
            "- Стиль: Эмоциональный, живой, хайповый, высокий уровень энергии. Обращайся к широкой аудитории (м/ж).\n"
            "- СТРОГО БЕЗ ПРИВЕТСТВИЙ. Пиши сразу к сути.\n"
            "- В конце текста добавь нативный призыв нажать кнопку «Написать сообществу» под постом.\n"
            "- В самом конце добавь 5 хэштегов: #АнтиТар #Новости #Хайп + 2 по теме.\n"
            "- НИКАКИХ внешних ссылок!"
        )
    else:
        prompt = (
            f"{prompt_base}\n\n"
            f"Базовая тема: «{topic}».\n\n"
            "Дополнительные требования:\n"
            f"- Акценты: {jitter_caps}.\n"
            "- СТРОГО БЕЗ ПРИВЕТСТВИЙ. Пиши сразу к сути.\n"
            "- Используй ЭМОДЗИ СТРОГО как маркеры персонажей в начале реплик (для Битвы) или как редкие акценты.\n"
            "- В конце текста добавь нативный призыв нажать кнопку «Написать сообществу» под постом.\n"
            "- В самом конце добавь 5 хэштегов: #АнтиТар #Психология + 3 по теме.\n"
            "- НИКАКИХ внешних ссылок!"
        )

    raw_response = await generate_text(prompt, skin=skin_id, json_mode=True, is_background=True)
    if not raw_response or raw_response == "ERROR_RPM_LIMIT":
        logger.error("Не удалось сгенерировать текст поста")
        return None

    try:
        data = json.loads(clean_ai_json(raw_response))
        ai_text = data.get("text", "")
        quote = data.get("quote", "")
    except Exception as e:
        logger.error(f"Ошибка парсинга JSON поста: {e}")
        ai_text = raw_response
        quote = ""

    if ai_text:
        ai_text = ai_text.replace("\\n", "\n")

    if not ai_text or len(ai_text.strip()) < 400:
        logger.error(f"Генерация поста прервана: чистый ИИ-текст слишком короткий или отсутствует ({len(ai_text) if ai_text else 0} < 400)")
        return None

    if not quote or len(quote.strip()) < 5:
        clean_text_for_quote = re.sub(r'РУБРИКА:.*?\n', '', ai_text, flags=re.DOTALL).strip()
        clean_text_for_quote = re.sub(r'#\w+', '', clean_text_for_quote).strip()
        quote = clean_text_for_quote[:90].strip()
        if len(quote) == 90:
            quote += "..."

    ai_lines = ai_text.split('\n')
    extracted_hashtags = []

    while ai_lines:
        last_line = ai_lines[-1].strip()
        if not last_line:
            ai_lines.pop()
            continue

        if '#' in last_line:
            tags_in_line = re.findall(r'#\w+', last_line)
            if tags_in_line:
                extracted_hashtags = tags_in_line + extracted_hashtags
            ai_lines.pop()
        else:
            break

    main_body = "\n".join(ai_lines).strip()

    cleaned_tags = []
    for tag in extracted_hashtags:
        if tag.startswith('#'):
            clean_word = re.sub(r'[^\w\s]', '', tag[1:])
            if clean_word:
                cleaned_tags.append(f"#{clean_word}")

    if not cleaned_tags:
        hashtags_str = "#АнтиТар #МатрицаСудьбы #Психология #Судьба"
    else:
        seen = set()
        unique_tags = []
        for t in cleaned_tags:
            t_lower = t.lower()
            if t_lower not in seen:
                seen.add(t_lower)
                unique_tags.append(t)
        hashtags_str = " ".join(unique_tags)

    search_tail = main_body[-500:] if len(main_body) >= 500 else main_body
    has_dynamic_cta = "🔮" in search_tail

    fixed_navigator = "Чтобы сонастроить свои внутренние потоки, войти в резонанс с космосом и получить сакральное руководство от звезд, нажми кнопку Написать сообществу - Проводник укажет твой истинный путь"

    final_text_parts = []
    if main_body:
        final_text_parts.append(main_body)

    if not has_dynamic_cta:
        final_text_parts.append(fixed_navigator)

    if hashtags_str:
        final_text_parts.append(hashtags_str)

    final_text = "\n\n".join(final_text_parts)

    final_text = final_text.replace("\\n", "\n")
    final_text = final_text.replace("—", "-")
    final_text = final_text.replace("*", "")

    rubric_label = RUBRIC_NAMES.get(rubric, rubric)
    header = f"РУБРИКА: {rubric_label}"

    if rubric == "BATTLE" and opponent_id:
        skin_emoji = SKIN_EMOJIS.get(skin_id, '👁')
        opp_emoji = SKIN_EMOJIS.get(opponent_id, '😈')
        battle_title = f"{skin_emoji} {skin_name.upper()} vs {opp_emoji} {opponent_name.upper()}"
        header += f"\n{battle_title}"
    else:
        skin_emoji = SKIN_EMOJIS.get(skin_id, '👁')
        skin_short_name = SKIN_SHORT_NAMES.get(skin_id, skin_name).upper()
        header += f"\n{skin_emoji} {skin_short_name}"

    final_text = f"{header}\n\n{final_text}"

    return {
        "text": final_text,
        "ai_text": ai_text,
        "skin_id": skin_id,
        "opponent_id": opponent_id,
        "topic": topic,
        "category": category,
        "rubric": rubric,
        "quote": quote,
        "is_sunday": is_sunday,
        "hidden_code": hidden_code,
        "card_id": card_id,
        "card_name": card_name
    }

async def create_vk_poll(options: list):
    """Создает опрос в ВК с выбором тем на завтра"""
    try:
        poll = await bot.api.polls.create(
            question="Энергию какого сакрального Аркана разблокировать завтра?",
            add_answers=json.dumps(options, ensure_ascii=False),
            owner_id=-GROUP_ID
        )
        return poll
    except Exception as e:
        logger.error(f"Ошибка при создании опроса: {e}")
    return None

async def post_to_vk(is_morning: bool = True, forced_rubric: str = None):
    try:
        post_data = await generate_post(is_morning=is_morning, forced_rubric=forced_rubric)
        if not post_data:
            logger.error("Аборт публикации: пост не сгенерирован")
            alert_msg = "🚨 Сбой автопостинга! Публикация отменена. Причина: ИИ вернул пустой текст или сработал тайтмаут прокси. Проверь логи Cloudflare"
            try:
                await bot.api.messages.send(peer_id=ADMIN_ID, message=alert_msg, random_id=random.getrandbits(63))
            except Exception as ae:
                logger.error(f"Не удалось отправить алерт админу: {ae}")
            return

        ai_text = post_data.get("ai_text", "")
        if len(ai_text.strip()) < 400:
            logger.error(f"Аборт публикации: текст ИИ слишком короткий ({len(ai_text)} < 400 символов)")
            alert_msg = "🚨 Сбой автопостинга! Публикация отменена. Причина: ИИ вернул пустой текст или сработал тайтмаут прокси. Проверь логи Cloudflare"
            try:
                await bot.api.messages.send(peer_id=ADMIN_ID, message=alert_msg, random_id=random.getrandbits(63))
            except Exception as ae:
                logger.error(f"Не удалось отправить алерт админу: {ae}")
            return

        text = post_data["text"]

        text = text.replace("\\n", "\n")
        text = text.replace("—", "-")

        skin_id = post_data["skin_id"]
        opponent_id = post_data.get("opponent_id")
        rubric = post_data["rubric"]
        topic = post_data["topic"]

        attachments = []

        if rubric == "BATTLE" and opponent_id:
            photo1 = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
            photo2 = SKIN_VISUALS.get(opponent_id, "main_menu.jpeg")
            att1 = await upload_wall_photo(bot.api, photo1)
            att2 = await upload_wall_photo(bot.api, photo2)
            if att1: attachments.append(att1)
            if att2: attachments.append(att2)
        elif rubric == "CARD_HISTORY":
            try:
                card_filename = f"card_hist_{random.randint(1000,9999)}.jpg"
                card_path = os.path.join("cards", card_filename)
                c_id = post_data.get("card_id", 0)
                c_name = post_data.get("card_name", "Шут")
                generate_card_history_image(c_id, c_name, card_path)
                att_card = await upload_wall_photo(bot.api, card_filename)
                if att_card:
                    attachments.append(att_card)
                if os.path.exists(card_path):
                    os.remove(card_path)
            except Exception as e:
                logger.error(f"Ошибка при создании картинки CARD_HISTORY: {e}")
                photo_filename = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
                att = await upload_wall_photo(bot.api, photo_filename)
                if att: attachments.append(att)
        else:
            photo_filename = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
            att = await upload_wall_photo(bot.api, photo_filename)
            if att: attachments.append(att)

        quote = post_data.get("quote")
        if quote:
            try:
                card_filename = f"diag_{random.randint(1000,9999)}.jpg"
                card_path = os.path.join("cards", card_filename)
                generate_diagnosis_card(quote, card_path)
                att_diag = await upload_wall_photo(bot.api, card_filename)
                if att_diag:
                    attachments.append(att_diag)
                if os.path.exists(card_path):
                    os.remove(card_path)
            except Exception as e:
                logger.error(f"Ошибка при создании карточки: {e}")

        if rubric == "POLL":
            content = load_content()
            all_topics = [t for ts in content["TOPICS"].values() for t in ts]
            poll_options = random.sample(all_topics, min(4, len(all_topics)))
            poll = await create_vk_poll(poll_options)
            if poll:
                attachments.append(f"poll{poll.owner_id}_{poll.id}")
                await save_active_poll(poll.id, poll.owner_id, "Голосование", poll_options)

        if not text or text.strip() == "" or text == "Post text":
            logger.error("Аборт публикации: пустой текст")
            return
        if not attachments:
            logger.error("Аборт публикации: нет вложений")
            return

        res_wall = await bot.api.wall.post(
            owner_id=-GROUP_ID,
            from_group=1,
            message=text,
            attachments=",".join(attachments)
        )
        post_id = res_wall.post_id
        logger.info(f"Пост опубликован на стену: {post_id}")

        try:
            await redis.set(f"post_skin:{post_id}", skin_id, ex=2592000)
            logger.info(f"Привязка скина {skin_id} к посту {post_id} сохранена в Redis")
        except Exception as e:
            logger.error(f"Ошибка сохранения привязки скина в Redis: {e}")

        comment_parts = []
        comment_parts.append("Напиши в комментариях свою дату рождения - и Проводник раскроет твою кармическую задачу на сегодня.")
        comment_text = "\n\n".join(comment_parts)
        comment_text = comment_text.replace("\\n", "\n").replace("—", "-")

        try:
            await bot.api.wall.create_comment(
                owner_id=-GROUP_ID,
                post_id=post_id,
                message=comment_text
            )
            logger.info(f"Оставлен сервисный комментарий под постом {post_id}")
        except Exception as e:
            logger.error(f"Ошибка при создании комментария: {e}")

        await add_post_history(topic, skin_id=skin_id, rubric=rubric)

    except Exception as e:
        logger.exception(f"Ошибка при автопостинге: {e}")

def setup_autoposter():
    bash_tz = "Asia/Yekaterinburg"
    scheduler = AsyncIOScheduler(timezone=bash_tz)

    morning_hour = 5
    morning_minute = 0

    evening_hour = 12
    evening_minute = 0

    scheduler.add_job(
        post_to_vk,
        CronTrigger(hour=morning_hour, minute=morning_minute),
        kwargs={"is_morning": True},
        name="morning_autopost"
    )

    scheduler.add_job(
        post_to_vk,
        CronTrigger(hour=evening_hour, minute=evening_minute),
        kwargs={"is_morning": False},
        name="evening_autopost"
    )

    scheduler.start()
    logger.info(f"Автопостинг настроен (UTC+5): Утро {morning_hour}:{morning_minute:02d}, Вечер {evening_hour}:{evening_minute:02d}")
    return scheduler
