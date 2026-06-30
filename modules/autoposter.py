import json
import random
import os
import datetime
from datetime import timezone, timedelta
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from vkbottle.bot import BotLabeler
from vkbottle import GroupEventType

import re
from modules.bot_init import bot
from ai_service import generate_text, clean_ai_json
from database.autoposter import (
    get_daily_used_content, get_active_poll, close_poll,
    save_hidden_promo, get_least_recent_rubric, save_active_poll
)
from modules.utils.visual import generate_diagnosis_card
from modules.utils.consts import SKIN_VISUALS, SKIN_DISPLAY_NAMES, SKIN_SHORT_NAMES, SKIN_EMOJIS, HIDDEN_CIPHER_WORDS
from modules.utils.photos import upload_wall_photo
from modules.utils.news import fetch_trending_news

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
    "TREND_WATCH": "ТРЕНД-АНАЛИЗ"
}

labeler = BotLabeler()

@labeler.raw_event(GroupEventType.WALL_POST_NEW, dataclass=dict)
async def ignore_self_wall_posts(event: dict):
    """
    Защита от самопостинга: игнорируем события о новых постах,
    если они созданы самим сообществом.
    """
    obj = event.get("object", {})
    from_id = obj.get("from_id", 0)
    if from_id == -GROUP_ID:
        return "ok"

@labeler.raw_event(GroupEventType.WALL_REPLY_NEW, dataclass=dict)
async def handle_diagnosis_comment(event: dict):
    """
    Интерактив «Вскрытие»: ответ на комментарий с датой рождения.
    """
    obj = event.get("object", {})
    text = obj.get("text", "")
    from_id = obj.get("from_id", 0)
    post_id = obj.get("post_id", 0)
    comment_id = obj.get("id", 0)

    if from_id <= 0: return "ok" # Игнорируем группы и пустые ID

    # Ищем дату рождения (ДД.ММ.ГГГГ или ДД.ММ)
    date_match = re.search(r"(\d{2}\.\d{2}(?:\.\d{2,4})?)", text)
    if date_match:
        birth_date = date_match.group(1)
        logger.info(f"Получен запрос на вскрытие от {from_id} под постом {post_id}: {birth_date}")

        from database import get_user
        user = await get_user(from_id)

        if user:
            # Данные пользователя
            purchased = user.get("purchased_sections", {})
            energy = user.get("balance", 0)
            city = user.get("birth_city", "неизвестен")

            user_context = f"Данные адепта: Дата {birth_date}, Город {city}, Энергия {energy}✨."
            prompt = (
                f"Проведи мгновенное «Вскрытие» адепта на основе его данных: {user_context}. "
                "Твой ответ должен быть максимально ядовитым, жестким, но психологически точным «диагнозом» его текущего состояния. "
                "Используй стиль Анти-Таро: цинизм, никакой пощады, метафоры матрицы и системных ошибок. "
                "Объем: 2-3 хлестких предложения. Без приветствий."
            )
        else:
            prompt = (
                f"Адепт прислал дату {birth_date}, но его нет в нашей базе. "
                "Твой ответ: «Ты — чистый лист в этой матрице. Заходи в бота, чтобы система тебя просканировала». "
                "Добавь к этому одну ядовитую фразу о том, что анонимы в системе не имеют веса."
            )

        diagnosis = await generate_text(prompt, skin="olesya")
        if diagnosis:
            try:
                await bot.api.wall.create_comment(
                    owner_id=-GROUP_ID,
                    post_id=post_id,
                    reply_to_comment=comment_id,
                    message=f"[id{from_id}|Адепт], {diagnosis}"
                )
            except Exception as e:
                logger.error(f"Ошибка при ответе на комментарий: {e}")

    return "ok"

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
    if forced_rubric:
        rubric = forced_rubric
        if rubric in ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"]:
            news_list = await fetch_trending_news()
            if news_list:
                selected_news = news_list[:4]
                topic = selected_news[0]["title"]
                news_context = "\n".join([f"НОВОСТЬ {i+1}: {n['title']}\nФАКТУРА: {n['description']}" for i, n in enumerate(selected_news)])
                category = "Новости"
                logger.info(f"Выбрана сводка новостей для принудительной рубрики {rubric}")
                tones = ["Эмоциональный разбор", "Высоковибрационный хайп", "Циничный инсайд"]
            else:
                logger.warning(f"Не удалось получить новости для принудительной рубрики {rubric}, используем стандартную тему")
                tones = ["Жесткий цинизм", "Дерзкая провокация"]
        elif rubric in ["SUPPORT", "FACT", "POLL"]:
            tones = ["Психологическое сочувствие", "Глубокий экспертный инсайт"]
        else:
            tones = ["Жесткий цинизм", "Дерзкая провокация"]
    elif is_morning:
        all_morning_rubrics = ["PROVOCATION", "MYTH_BUST", "BATTLE", "PRACTICUM"]
        rubric = await get_least_recent_rubric(all_morning_rubrics)
        tones = ["Жесткий цинизм", "Дерзкая провокация"]
    else:
        # Вечерний пост: 100% новостной хайп (согласно ТЗ 50% от общего числа постов)
        news_list = await fetch_trending_news()
        if news_list:
            news_rubrics = ["NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH"]
            rubric = await get_least_recent_rubric(news_rubrics)
            selected_news = news_list[:4]
            topic = selected_news[0]["title"]
            news_context = "\n".join([f"НОВОСТЬ {i+1}: {n['title']}\nФАКТУРА: {n['description']}" for i, n in enumerate(selected_news)])
            category = "Новости"
            logger.info(f"Выбрана сводка новостей для рубрики {rubric}")
            tones = ["Эмоциональный разбор", "Высоковибрационный хайп", "Циничный инсайд"]
        else:
            # Fallback if news fetch fails
            logger.warning("Не удалось получить новости, откат к стандартным рубрикам")
            all_evening_rubrics = ["SUPPORT", "FACT", "POLL"]
            rubric = await get_least_recent_rubric(all_evening_rubrics)

            if all_available_topics:
                category, topic = random.choice(all_available_topics)
            else:
                category, topic = random.choice([(c, t) for c, ts in topics_by_category.items() for t in ts])

            tones = ["Психологическое сочувствие", "Глубокий экспертный инсайт"]

    tone = random.choice(tones)

    # ГЕНЕРАЦИЯ СКРЫТОГО ШИФРА
    cipher_base = random.choice(HIDDEN_CIPHER_WORDS)
    cipher_num = random.randint(100, 999)
    hidden_code = f"{cipher_base}-{cipher_num}"
    energy_reward = random.randint(50, 200)

    # Сохраняем код в БД
    await save_hidden_promo(hidden_code, energy_reward)
    logger.info(f"Сгенерирован скрытый шифр для поста: {hidden_code} на {energy_reward} ✨")

    cipher_masks = [
        f"как технический баг или системную ошибку (например: 'реальность выдала {hidden_code}')",
        f"как сакральный номер в реестре судеб (например: 'твой индекс в матрице — {hidden_code}')",
        f"как мистическую частоту или код доступа (например: 'ключ к переходу — {hidden_code}')",
        f"как количество накопленных грехов или очков кармы (например: 'счетчик тени замер на {hidden_code}')",
        f"как зашифрованное время или координату (например: 'встречаемся в точке {hidden_code}')",
        f"как индекс уровня хайпа или аномалии (например: 'уровень шума в эфире — {hidden_code}')",
        f"как номер старого архивного дела или протокола (например: 'согласно протоколу {hidden_code}')"
    ]
    chosen_mask = random.choice(cipher_masks)

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

    # Рандомизация структуры для борьбы с «одной схемой»
    jitter_length = random.choice(["короткий (3-4 предложения)", "средний (5-7 предложений)", "динамичный (смена ритма)"])
    jitter_style = random.choice(["используй списки через дефисы", "используй списки через магические символы (✦, ⚡)", "сплошной текст с резкими переходами"])
    jitter_caps = random.choice(["используй КАПС для акцентов на 3-5 словах", "не используй КАПС совсем", "используй КАПС только для финального вывода"])

    # Виральные триггеры для определенных рубрик
    viral_instruction = ""
    if rubric in ["PROVOCATION", "MYTH_BUST"]:
        viral_instruction = (
            "\n\nИСПОЛЬЗУЙ РАДИКАЛЬНЫЕ ТЕЗИСЫ: «Таро — это костыль для тех, кто боится принимать решения» или «Денежные марафоны — это налог на глупость». "
            "Заканчивай пост вопросом, который противопоставляет читателя остальным: «Ты готов признать, что ты прокрастинируешь, или продолжишь тешить себя медитациями?»."
        )

    # Формирование специфических инструкций под рубрику
    rubric_instructions = {
        "PROVOCATION": (
            f"Это ультра-короткий пост-провокация. Объем: {jitter_length}. "
            "Задай один крайне неудобный и хлесткий вопрос в лоб, который заставит читателя чувствовать дискомфорт от своей пассивности. "
            f"Никаких советов и практикумов. Только удар по гордости и призыв в бота.{viral_instruction}"
        ),
        "MYTH_BUST": (
            f"Разрушение мифов. Объем: {jitter_length}. Структура: {jitter_style}. "
            "Возьми популярное заблуждение в эзотерике (ретроградный меркурий, марафоны желаний, денежные аффирмации) "
            f"и жестко разнеси его с позиции приземленной психологии и твоего персонажа. Покажи, почему это ловушка для дураков.{viral_instruction}"
        ),
        "BATTLE": (
            f"Битва Архетипов. Это диалог-стычка между тобой ({skin_name}) и персонажем {opponent_name}. "
            f"Вы спорите на тему «{topic}». КРИТИЧЕСКОЕ ТРЕБОВАНИЕ: персонажи должны агрессивно спорить, "
            "сталкиваться лбами и жестко критиковать подходы друг друга. Один давит холодным расчетом, "
            "другой — ядовитой правдой или мистикой. Диалог должен быть похож на острую словесную дуэль с переходом на личности, "
            "без скучного обмена любезностями. Ты гнешь свою линию, {opponent_name} — свою. "
            "Диалог должен быть динамичным, острым и коротким. Каждая реплика должна начинаться с новой строки в формате:\n"
            f"{SKIN_EMOJIS.get(skin_id, '👁')} {SKIN_SHORT_NAMES.get(skin_id, skin_id)}: Текст реплики...\n"
            f"{SKIN_EMOJIS.get(opponent_id, '👁')} {SKIN_SHORT_NAMES.get(opponent_id, opponent_id)}: Текст реплики...\n"
            "В конце диалога обязательно добавь свой финальный едкий вывод без префикса имени."
        ),
        "PRACTICUM": (
            f"Классический жесткий практикум. Вскрой боль темы и дай 3-5 конкретных шагов. Структура: {jitter_style}. "
            f"Объем: {jitter_length}."
        ),
        "SUPPORT": (
            f"Сакральная поддержка. В этом посте ты не ругаешь, а глубоко сочувствуешь боли читателя. Объем: {jitter_length}. "
            "Скажи, что быть не в порядке — это нормально. Дай мягкий, обволакивающий совет, как трансформировать эту боль в ресурс."
        ),
        "FACT": (
            f"Мистический факт. Объем: {jitter_length}. "
            "Расскажи удивительный, малоизвестный факт из истории мистики, хиромантии или психологии Юнга, "
            "связанный с темой поста. Подача должна быть авторитетной и глубокой."
        ),
        "POLL": (
            f"Интерактивный опрос. Объем: {jitter_length}. "
            "Напиши интригующее вступление к теме, подведи к тому, что выбор за читателем. "
            "Текст должен обрываться на вопросе, на который люди ответят в опросе ниже."
        ),
        "NEWS_BREAKDOWN": (
            f"СВОДКА НОВОСТЕЙ ДЛЯ РАЗБОРА:\n{news_context}\n\n"
            "ЗАДАНИЕ: \n"
            "1. Напиши краткую и хлесткую сводку этих 3-4 новостей. Каждой новости — по 1-2 предложения, чтобы читатель понял суть и фактуру. Пиши максимально живо, хайпово, как горячие сплетни дня. \n"
            f"2. Твой ЕДИНЫЙ авторский комментарий как {skin_name} по всей этой повестке дня. Препарируй ситуацию через свою эзотерическую или психологическую призму. Почему это произошло с точки зрения кармы или подсознания? \n"
            "3. Резкий вывод и призыв. \n"
            "Вайб: HIGH VIBE, сочные эмоции, используй уместные эмодзи (✨, 🔥, 🔮, 💸), обращайся ко всей аудитории (и к парням, и к девчонкам)."
        ),
        "STAR_SYNASTRY": (
            f"СВОДКА НОВОСТЕЙ ДЛЯ РАЗБОРА:\n{news_context}\n\n"
            "ЗАДАНИЕ: \n"
            "1. Напиши краткую сводку новостей, называя ключевые имена и факты. \n"
            "2. Твой авторский 'Звездный разбор': выбери самых ярких героев из этих новостей и разбери их совместимость, причины краха или их архетипы. \n"
            "3. Пиши сочно, с инсайдами, которые 'шепчут звезды'. Тон: как в закрытом элитном клубе."
        ),
        "TREND_WATCH": (
            f"СВОДКА НОВОСТЕЙ ДЛЯ РАЗБОРА:\n{news_context}\n\n"
            "ЗАДАНИЕ: \n"
            "1. Напиши краткую сводку новостей. \n"
            "2. Твой 'Тренд-анализ': разбери, куда катится мир согласно этой сводке. Это 'знамение конца' или 'новая эра'? Дай экспертный прогноз, как это повлияет на обычных людей. \n"
            "3. Пиши энергично, дерзко, используй метафоры будущего и эзотерики."
        )
    }

    # Логика разделения шифра по воскресеньям
    is_sunday = now.weekday() == 6
    if is_sunday:
        cipher_parts = hidden_code.split('-')
        part1, part2 = cipher_parts[0], cipher_parts[1]
        cipher_instruction = (
            f"КРИТИЧЕСКОЕ ЗАДАНИЕ: Сегодня воскресенье, поэтому мы делим шифр на две части. "
            f"Вшей в середину текста ПЕРВУЮ ЧАСТЬ ШИФРА: {part1}. "
            f"Вплети её {chosen_mask}. "
            "Она должна выглядеть как естественная часть повествования."
        )
    else:
        cipher_instruction = (
            f"КРИТИЧЕСКОЕ ЗАДАНИЕ: Вшей в текст поста скрытый игровой шифр: {hidden_code}. "
            f"Вплети его {chosen_mask}. "
            "Он НЕ должен быть в конце или начале. Он должен быть органично вшит в середину одного из абзацев. "
            "Код должен быть написан именно так: КАПСОМ, латиницей, через дефис. "
            "НЕ делай на нем акцент, он должен выглядеть как естественная часть повествования."
        )

    # Инструкция по виральному вызову в конце
    ego_call = "В конце поста добавь циничную приписку: «Перешли этот пост тому, кто до сих пор верит в удачу, а не в стратегию. Пусть его тоже проберет»."

    prompt_base = (
        f"Текущая дата: {current_date_str}, день недели: {current_day}. "
        "Напиши виральный пост для паблика Анти-Тар.\n"
        f"Твоя роль: {skin_name}. Твой эмоциональный тон: {tone}.\n"
        f"Рубрика поста: {rubric}. Инструкция: {rubric_instructions.get(rubric)}\n\n"
        f"{cipher_instruction}\n\n"
        f"{ego_call}\n\n"
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
            "- Текст должен быть нативным, без приветствий и лишней воды.\n"
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
            "- Используй ЭМОДЗИ СТРОГО как маркеры персонажей в начале реплик (для Битвы) или как редкие акценты.\n"
            "- Текст должен быть нативным, без приветствий и лишней воды.\n"
            "- В конце текста добавь нативный призыв нажать кнопку «Написать сообществу» под постом.\n"
            "- В самом конце добавь 5 хэштегов: #АнтиТар #Психология + 3 по теме.\n"
            "- НИКАКИХ внешних ссылок!"
        )

    # Мы передаем skin_id, и generate_text сам возьмет нужный TOV из SKIN_MAP в prompts/personas.py
    raw_response = await generate_text(prompt, skin=skin_id, json_mode=True)
    if not raw_response:
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

    # Внедрение заголовка рубрики
    rubric_label = RUBRIC_NAMES.get(rubric, rubric)
    header = f"РУБРИКА: {rubric_label}"

    if rubric == "BATTLE" and opponent_id:
        skin_emoji = SKIN_EMOJIS.get(skin_id, '👁')
        opp_emoji = SKIN_EMOJIS.get(opponent_id, '😈')
        battle_title = f"{skin_emoji} {skin_name.upper()} vs {opp_emoji} {opponent_name.upper()}"
        header += f"\n{battle_title}"

    final_text = f"{header}\n\n{final_text}"

    return {
        "text": final_text,
        "skin_id": skin_id,
        "opponent_id": opponent_id,
        "topic": topic,
        "category": category,
        "rubric": rubric,
        "quote": quote,
        "is_sunday": is_sunday,
        "hidden_code": hidden_code
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

async def post_to_vk(is_morning: bool = True, forced_rubric: str = None):
    try:
        post_data = await generate_post(is_morning=is_morning, forced_rubric=forced_rubric)
        if not post_data:
            return

        text = post_data["text"]

        # Принудительная очистка текста перед публикацией
        text = text.replace("\\n", "\n")  # Превращаем строковые \n в реальные
        text = text.replace("—", "-")  # Убиваем длинные тире

        skin_id = post_data["skin_id"]
        opponent_id = post_data.get("opponent_id")
        rubric = post_data["rubric"]
        topic = post_data["topic"]

        # --- СБОР ВЛОЖЕНИЙ (ЕДИНАЯ СЕТКА) ---
        attachments = []

        # 1. Основные фото (Персонажи)
        if rubric == "BATTLE" and opponent_id:
            photo1 = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
            photo2 = SKIN_VISUALS.get(opponent_id, "main_menu.jpeg")
            att1 = await upload_wall_photo(bot.api, photo1)
            att2 = await upload_wall_photo(bot.api, photo2)
            if att1: attachments.append(att1)
            if att2: attachments.append(att2)
        else:
            photo_filename = SKIN_VISUALS.get(skin_id, "main_menu.jpeg")
            att = await upload_wall_photo(bot.api, photo_filename)
            if att: attachments.append(att)

        # 2. Дополнительная карта (20% шанс, кроме опросов)
        if random.random() < 0.2 and rubric != "POLL":
            card_id = random.randint(0, 77)
            att_card = await upload_wall_photo(bot.api, f"{card_id}.jpeg")
            if att_card:
                attachments.append(att_card)

        # 3. Карточка-диагноз (генерируется из цитаты ИИ)
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

        # 4. Опрос (добавляется в конец списка вложений)
        if rubric == "POLL":
            content = load_content()
            all_topics = [t for ts in content["TOPICS"].values() for t in ts]
            poll_options = random.sample(all_topics, min(4, len(all_topics)))
            poll = await create_vk_poll(poll_options)
            if poll:
                attachments.append(f"poll{poll.owner_id}_{poll.id}")
                await save_active_poll(poll.id, poll.owner_id, "Голосование", poll_options)

        # Валидация перед отправкой
        if not text or text.strip() == "" or text == "Post text":
            logger.error("Аборт публикации: пустой текст")
            return
        if not attachments:
            logger.error("Аборт публикации: нет вложений")
            return

        # Публикация на Стену сообщества (единый запрос для сетки)
        res_wall = await bot.api.wall.post(
            owner_id=-GROUP_ID,
            from_group=1,
            message=text,
            attachments=",".join(attachments)
        )
        post_id = res_wall.post_id
        logger.info(f"Пост опубликован на стену: {post_id}")

        # АВТОМАТИЧЕСКИЙ КОММЕНТАРИЙ (Вскрытие + Вторая часть шифра)
        comment_parts = []

        # 1. Триггер "Вскрытие"
        comment_parts.append("Напиши в комментариях свою дату рождения — и Проводник вскроет твой главный блок на сегодня.")

        # 2. Вторая часть шифра по воскресеньям
        if post_data.get("is_sunday"):
            hidden_code = post_data.get("hidden_code", "")
            if "-" in hidden_code:
                cipher_parts = hidden_code.split("-")
                if len(cipher_parts) > 1:
                    part2 = cipher_parts[1]
                    comment_parts.append(f"Вторая часть ключа найдена в обломках матрицы: {part2}")

        comment_text = "\n\n".join(comment_parts)
        try:
            res_comm = await bot.api.wall.create_comment(
                owner_id=-GROUP_ID,
                post_id=post_id,
                message=comment_text
            )
            # Закрепление комментария (требует прав или использования user_api)
            # В vkbottle/VK API метод wall.pin работает только для постов.
            # Для комментариев "закрепления" как такового нет,
            # но первый комментарий от имени группы обычно виден лучше всего.
            logger.info(f"Оставлен сервисный комментарий под постом {post_id}")
        except Exception as e:
            logger.error(f"Ошибка при создании комментария: {e}")

        # Записываем в историю публикаций (используем и тему и скин для лога 72ч)
        from database.autoposter import add_post_history
        await add_post_history(topic, skin_id=skin_id, rubric=rubric)

    except Exception as e:
        logger.exception(f"Ошибка при автопостинге: {e}")

def setup_autoposter():
    # Таймзона Башкортостана (UTC+5)
    bash_tz = "Asia/Yekaterinburg"
    scheduler = AsyncIOScheduler(timezone=bash_tz)

    # 🌅 Утренний выход: ровно 08:00
    morning_hour = 5
    morning_minute = 0

    # 🌌 Вечерний выход: ровно 19:00
    evening_hour = 12
    evening_minute = 0

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
