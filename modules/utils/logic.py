import random
import json
import string
import datetime
from loguru import logger
from database import get_user_state, update_user
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
            from database import get_user
            current_user = await get_user(vk_id)
            if not current_user:
                return
            current_last_bonus = current_user.get("last_daily_bonus_date")
            if current_last_bonus:
                try:
                    if now_date <= datetime.date.fromisoformat(current_last_bonus):
                        return
                except ValueError: pass
            current_balance = int(current_user.get("balance", 0) or 0)
            visit_streak = current_user.get("visit_streak", 0)
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
                "visit_streak": visit_streak
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

def calculate_destiny_card(birth_date_str: str) -> int:
    """
    Рассчитывает Аркан судьбы по дате рождения (1-22).
    Пример: 15.06.1991 -> 1+5+0+6+1+9+9+1 = 32 -> 3+2 = 5 (Аркан V).
    Если 22 - оставляем 22.
    """
    if not birth_date_str:
        return 1

    # Очищаем дату от всего кроме цифр
    digits = [int(d) for d in birth_date_str if d.isdigit()]
    if not digits:
        return 1

    s = sum(digits)

    while s > 22:
        # Суммируем цифры полученного числа
        s = sum(int(d) for d in str(s))

    return s

def generate_shadow_cipher() -> str:
    """Генерирует уникальный 6-значный теневой шифр"""
    chars = string.ascii_uppercase + string.digits
    # Исключаем похожие символы для удобства (O и 0, I и 1)
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    return ''.join(random.choice(chars) for _ in range(6))
