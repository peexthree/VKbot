import random
import json
import string
import datetime
import re
from loguru import logger
from database import get_user_state, update_user, get_user
from cache import acquire_lock, release_lock

async def get_fsm_step(vk_id: int) -> dict | None:
    data = await get_user_state(vk_id)
    if data:
        try:
            return json.loads(data)
        except Exception:
            # Fallback if state is stored as a raw string
            return {"step": data}
    return None

async def check_and_give_daily_bonus(vk_id: int, user: dict | None, peer_id: int):
    if not user:
        return
    last_bonus_date_str = user.get("last_daily_bonus_date")
    now_date = datetime.datetime.now(datetime.timezone.utc).date()
    should_give = False
    if not last_bonus_date_str:
        should_give = True
    else:
        try:
            last_bonus_date = datetime.date.fromisoformat(last_bonus_date_str)
            if now_date > last_bonus_date:
                should_give = True
        except ValueError:
            should_give = True
    if should_give:
        lock_key = f"daily_bonus_lock:{vk_id}"
        if not await acquire_lock(lock_key, ttl=10):
            return
        try:
            # Получаем свежие данные пользователя под локом
            fresh_user = await get_user(vk_id)
            if not fresh_user:
                return

            current_last_bonus = fresh_user.get("last_daily_bonus_date")
            if current_last_bonus:
                try:
                    if now_date <= datetime.date.fromisoformat(current_last_bonus):
                        return
                except ValueError: pass

            current_balance = int(fresh_user.get("balance", 0) or 0)
            visit_streak = fresh_user.get("visit_streak", 0)

            if current_last_bonus:
                try:
                    last_bonus_date = datetime.date.fromisoformat(current_last_bonus)
                    if (now_date - last_bonus_date).days == 1:
                        visit_streak += 1
                    else:
                        visit_streak = 1
                except ValueError:
                    visit_streak = 1
            else:
                visit_streak = 1

            # Эскалация бонуса в зависимости от стрика
            bonus_amount = 100 + min(visit_streak * 20, 400) # Макс бонус 500
            new_balance = current_balance + bonus_amount

            await update_user(vk_id, {
                "balance": new_balance,
                "last_daily_bonus_date": now_date.isoformat(),
                "visit_streak": visit_streak,
                "rituals_count": (fresh_user.get("rituals_count", 0) or 0) + 1
            })
            user["balance"] = new_balance
            user["last_daily_bonus_date"] = now_date.isoformat()
            user["visit_streak"] = visit_streak

            if visit_streak >= 7:
                from modules.bot_init import bot
                from modules.skins import unlock_skin
                await unlock_skin(bot.api, vk_id, "vanga")
            try:
                from modules.bot_init import bot
                bonus_text = f"🎁 ТВОЙ ЕЖЕДНЕВНЫЙ ДАР: +{bonus_amount} Энергии звезд.\n"
                if visit_streak > 1:
                    bonus_text += f"🔥 Стрик: {visit_streak} дней! Бонус увеличен.\n"
                bonus_text += f"Возвращайся завтра. Твой баланс: {new_balance} ✨."

                await bot.api.messages.send(
                    peer_id=peer_id,
                    message=bonus_text,
                    random_id=random.getrandbits(63)
                )
            except Exception as e:
                logger.error(f"Ошибка: {str(e)}")
        finally:
            await release_lock(lock_key)

def calculate_user_rank(user: dict) -> tuple[int, str]:
    """Рассчитывает уровень и ранг пользователя"""
    unlocked_cards = user.get("unlocked_cards", {})
    if isinstance(unlocked_cards, list):
        unlocked_count = len(unlocked_cards)
    elif isinstance(unlocked_cards, dict):
        unlocked_count = len(unlocked_cards)
    else:
        unlocked_count = 0

    total_cards_received = user.get("total_cards_received", 0) or 0
    level = 1 + (unlocked_count // 5) + (total_cards_received // 10)

    rank_names = [
        "Неофит", "Послушник", "Искатель", "Адепт", "Проводник",
        "Мастер Теней", "Верховный Жрец", "Хранитель Ключей", "Магистр Матрицы"
    ]
    rank = rank_names[min(max(0, level - 1) // 3, len(rank_names)-1)]
    return level, rank

def calculate_exp_progress(user: dict) -> int:
    """Рассчитывает прогресс опыта до следующего уровня в процентах"""
    unlocked_cards = user.get("unlocked_cards", {})
    if isinstance(unlocked_cards, list):
        unlocked_count = len(unlocked_cards)
    elif isinstance(unlocked_cards, dict):
        unlocked_count = len(unlocked_cards)
    else:
        unlocked_count = 0

    total_cards_received = user.get("total_cards_received", 0) or 0

    # Исходя из формулы уровня: level = 1 + (unlocked_count // 5) + (total_cards_received // 10)
    # Уровень повышается при достижении каждых 5 открытых карт ИЛИ каждых 10 полученных раскладов.
    # Прогресс — это то, насколько пользователь близок к следующему повышению уровня
    # по любому из этих двух путей.
    card_progress = (unlocked_count % 5) * 20
    reading_progress = (total_cards_received % 10) * 10

    return max(card_progress, reading_progress)

def get_syndicate_rank(count: int) -> str:
    """Возвращает ранг в системе"""
    if count >= 10: return "Теневой Архитектор"
    if count >= 5: return "Теневой Кардинал"
    if count >= 3: return "Мастер Вербовки"
    if count >= 1: return "Вербовщик"
    return "Одиночка"

def reduce_to_22(n: int) -> int:
    """
    Приводит число к системе 22 (Матрица Ладини).
    Если больше 22, вычитает 22 до тех пор, пока не станет <= 22.
    """
    if n <= 0: return 22
    while n > 22:
        n -= 22
    return n

def calculate_destiny_card(birth_date_str: str) -> int:
    """
    Рассчитывает Главный Аркан Судьбы (Личность) по дню рождения.
    Использует правило вычитания 22.
    """
    if not birth_date_str:
        return 1

    # Ищем первое число (день)
    match = re.search(r"(\d{1,2})", birth_date_str)
    if not match: return 1

    day = int(match.group(1))
    return reduce_to_22(day)

def calculate_purpose_arcana(birth_date_str: str) -> int:
    """
    Рассчитывает Аркан Предназначения (День + Месяц + Год).
    Каждый элемент приводится к 22 отдельно, затем сумма приводится к 22.
    """
    date_str = extract_russian_date(birth_date_str)

    if not date_str:
        return 1

    parts = date_str.split('.')
    d = int(parts[0])
    m = int(parts[1])
    y = int(parts[2]) if len(parts) > 2 else 2000

    d_red = reduce_to_22(d)
    m_red = reduce_to_22(m) # Месяц всегда <= 12
    y_sum = sum(int(digit) for digit in str(y))
    y_red = reduce_to_22(y_sum)

    return reduce_to_22(d_red + m_red + y_red)

def generate_shadow_cipher() -> str:
    """Генерирует уникальный 6-значный теневой шифр"""
    chars = string.ascii_uppercase + string.digits
    # Исключаем похожие символы для удобства (O и 0, I и 1)
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    return ''.join(random.choice(chars) for _ in range(6))

def transliterate(text: str) -> str:
    """Простая транслитерация кириллицы в латиницу"""
    mapping = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    return "".join(mapping.get(c, c) for c in text.lower())

def get_safe_tags(user: dict) -> list[str]:
    """Безопасное извлечение тегов пользователя с фильтрацией мусора"""
    tags = user.get("tags")
    if not tags:
        return []

    if isinstance(tags, str):
        try:
            # Пытаемся распарсить как JSON
            tags = json.loads(tags)
        except Exception:
            # Если это строка вида "['tag']", используем literal_eval
            if tags.startswith('[') and tags.endswith(']'):
                try:
                    import ast
                    tags = ast.literal_eval(tags)
                except Exception:
                    return []
            else:
                # Если просто строка, оборачиваем в список
                tags = [tags]

    if not isinstance(tags, list):
        return []

    # Фильтруем пустые строки, слишком короткие теги и технические символы
    clean_tags = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        # Тег должен быть осмысленным и не быть техническим символом
        if len(t) > 2 and t not in ["[", "]", "{", "}", "None", "null"]:
            clean_tags.append(t)

    return clean_tags

def slugify(text: str) -> str:
    """Создает безопасный латинский слаг из кириллической строки"""
    # 1. Транслитерация
    text = transliterate(text)
    # 2. Пробелы в нижнее подчеркивание
    text = text.replace(" ", "_")
    # 3. Очистка от всего, кроме латиницы, цифр и _
    text = re.sub(r'[^a-z0-9_]', '', text)
    # 4. Убираем двойные подчеркивания
    text = re.sub(r'_+', '_', text)
    return text.strip("_")

def clean_topic_ref(text: str) -> str:
    """Очищает тему для использования в параметре ref (лимит 40 символов)"""
    slug = slugify(text)
    return slug[:40].strip("_")

def extract_russian_date(text: str) -> str | None:
    """
    Извлекает и нормализует дату из русского текста.
    Поддерживает: 13.12.2006, 13.12, 13 декабря 2006, 13 дек, 13.12.06 и т.д.
    """
    month_map = {
        'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04', 'май': '05', 'июн': '06',
        'июл': '07', 'авг': '08', 'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12',
        'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04', 'мая': '05', 'июня': '06',
        'июля': '07', 'августа': '08', 'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12',
        'сент': '09', 'нояб': '11'
    }

    text = text.lower().strip()

    # 1. Цифровой формат: ДД.ММ.ГГГГ или ДД.ММ ГГГГ или ДД.ММ.ГГ или ДД.ММ
    numeric_match = re.search(r"(\d{1,2})[./-]\s*(\d{1,2})(?:[./\s-]\s*(\d{2,4}))?", text)
    if numeric_match:
        d, m = numeric_match.group(1), numeric_match.group(2)
        y = numeric_match.group(3)

        d = d.zfill(2)
        m = m.zfill(2)
        # Базовая валидация месяца и дня
        if int(m) > 12 or int(d) > 31: return None

        if y:
            if len(y) == 2:
                y = "20" + y if int(y) < 30 else "19" + y
            return f"{d}.{m}.{y}"
        return f"{d}.{m}"

    # 2. Текстовый формат: 13 декабря 2006
    month_names = "|".join(sorted(month_map.keys(), key=len, reverse=True))
    text_match = re.search(fr"(\d{{1,2}})\s+({month_names})(?:\s+(\d{{2,4}}))?", text)
    if text_match:
        d = text_match.group(1).zfill(2)
        m_name = text_match.group(2)
        m = month_map.get(m_name)
        y = text_match.group(3)

        if int(d) > 31: return None

        if y:
            if len(y) == 2:
                y = "20" + y if int(y) < 30 else "19" + y
            return f"{d}.{m}.{y}"
        return f"{d}.{m}"

    return None
