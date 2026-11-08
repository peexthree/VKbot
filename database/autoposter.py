import datetime
import random
from typing import List
from loguru import logger
from database.config import URL, KEY, HEADERS
import database.core as core

async def get_recent_topics(limit: int = 30) -> List[str]:
    """Возвращает список последних опубликованных тем"""
    if not URL or not KEY or core.session is None: return []
    try:
        url = f"{URL}/rest/v1/post_history?select=topic_name&order=published_at.desc&limit={limit}"
        async with core.session.get(url, headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return [item["topic_name"] for item in data]
    except Exception as e:
        logger.error(f"Error in get_recent_topics: {e}")
    return []

async def add_post_history(topic_name: str, skin_id: str = None, rubric: str = None):
    """Записывает публикацию поста в историю и в ежедневный лог"""
    if not URL or not KEY or core.session is None: return False

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 1. Запись в общую историю
    payload_history = {
        "topic_name": topic_name,
        "published_at": now_iso
    }

    # 2. Запись в ежедневный лог (для контроля повторов за 72ч)
    payload_daily = {
        "skin_id": skin_id or "unknown",
        "topic_name": topic_name,
        "rubric": rubric or "unknown",
        "published_at": now_iso
    }

    try:
        async with core.session.post(f"{URL}/rest/v1/post_history", headers=HEADERS, json=payload_history) as r:
            logger.info(f"Post history updated: {r.status}")

        async with core.session.post(f"{URL}/rest/v1/post_daily_log", headers=HEADERS, json=payload_daily) as r:
            logger.info(f"Daily log updated: {r.status}")

        return True
    except Exception as e:
        logger.error(f"Error in add_post_history: {e}")
    return False

async def get_daily_used_content():
    """Возвращает персонажей, темы и рубрики, использованные за последние 72 часа"""
    if not URL or not KEY or core.session is None: return [], [], []
    try:
        # 72 часа назад (увеличили память для большего разнообразия)
        time_limit = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=72)).isoformat()
        # Добавляем сортировку, чтобы понимать порядок использования
        url = f"{URL}/rest/v1/post_daily_log?select=skin_id,topic_name,rubric,published_at&published_at=gt.{time_limit}&order=published_at.desc"
        async with core.session.get(url, headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                skins = [item.get("skin_id") for item in data if item.get("skin_id")]
                topics = [item.get("topic_name") for item in data if item.get("topic_name")]
                rubrics = [item.get("rubric") for item in data if item.get("rubric")]
                return skins, topics, rubrics
    except Exception as e:
        logger.error(f"Error in get_daily_used_content: {e}")
        return [], [], []
    return [], [], []

async def get_least_recent_rubric(pool: List[str]) -> str:
    """Находит рубрику из пула, которая использовалась дольше всего назад (LRU)"""
    if not URL or not KEY or core.session is None or not pool:
        return random.choice(pool) if pool else "unknown"
    try:
        # Берем историю за последние 7 дней для надежного LRU
        time_limit = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
        url = f"{URL}/rest/v1/post_daily_log?select=rubric,published_at&published_at=gt.{time_limit}&order=published_at.desc"
        async with core.session.get(url, headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                last_used = {}
                for item in data:
                    rub = item.get("rubric")
                    if rub in pool and rub not in last_used:
                        last_used[rub] = item.get("published_at")

                unused = [r for r in pool if r not in last_used]
                if unused:
                    return random.choice(unused)

                return min(last_used, key=last_used.get)
    except Exception as e:
        logger.error(f"Error in get_least_recent_rubric: {e}")
    return random.choice(pool)

async def save_active_poll(poll_id: int, owner_id: int, topic_name: str, options: list):
    """Сохраняет активный опрос в базу"""
    if not URL or not KEY or core.session is None: return False
    payload = {
        "poll_id": poll_id,
        "owner_id": owner_id,
        "topic_name": topic_name,
        "options": options,
        "is_active": True
    }
    try:
        async with core.session.post(f"{URL}/rest/v1/active_polls", headers=HEADERS, json=payload) as r:
            return r.status in (200, 201, 204)
    except Exception as e:
        logger.error(f"Error in save_active_poll: {e}")
    return False

async def get_active_poll():
    """Возвращает последний активный опрос"""
    if not URL or not KEY or core.session is None: return None
    try:
        url = f"{URL}/rest/v1/active_polls?select=*&is_active=eq.true&order=created_at.desc&limit=1"
        async with core.session.get(url, headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return data[0] if data else None
    except Exception as e:
        logger.error(f"Error in get_active_poll: {e}")
    return None

async def close_poll(id: int):
    """Помечает опрос как закрытый"""
    if not URL or not KEY or core.session is None: return False
    try:
        url = f"{URL}/rest/v1/active_polls?id=eq.{id}"
        async with core.session.patch(url, headers=HEADERS, json={"is_active": False}) as r:
            return r.status in (200, 204)
    except Exception as e:
        logger.error(f"Error in close_poll: {e}")
    return False

async def record_post_click(vk_id: int, topic_name: str):
    """Записывает клик пользователя и инкрементирует общий счетчик темы"""
    if not URL or not KEY or core.session is None: return False

    # 1. Записываем детальный клик
    click_payload = {
        "vk_id": vk_id,
        "topic_name": topic_name,
        "clicked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    try:
        # Пишем клик
        await core.session.post(f"{URL}/rest/v1/post_clicks", headers=HEADERS, json=click_payload)

        # 2. Инкрементируем счетчик в post_history через RPC (рекомендуется)
        # Если RPC нет, можно попробовать PATCH, но нужно найти ID последнего поста с этой темой
        # Давай попробуем RPC, это надежнее
        await core.call_rpc("increment_post_clicks", {"p_topic_name": topic_name})

        return True
    except Exception as e:
        logger.error(f"Error in record_post_click: {e}")
    return False

async def get_rubric_ctr_stats(days: int = 45) -> dict:
    """Средние клики по рубрикам за период (для CTR-взвешивания ротации).

    Рубрики живут в post_daily_log, клики - в post_history; связка по topic_name.
    """
    if not URL or not KEY or core.session is None: return {}
    time_limit = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    try:
        async with core.session.get(
            f"{URL}/rest/v1/post_daily_log?select=rubric,topic_name&published_at=gt.{time_limit}",
            headers=HEADERS
        ) as r:
            if r.status not in (200, 206): return {}
            logs = await r.json()

        async with core.session.get(
            f"{URL}/rest/v1/post_history?select=topic_name,clicks&published_at=gt.{time_limit}",
            headers=HEADERS
        ) as r:
            if r.status not in (200, 206): return {}
            history = await r.json()

        clicks_by_topic = {}
        for h in history:
            try:
                clicks_by_topic[h.get("topic_name")] = int(h.get("clicks", 0) or 0)
            except (ValueError, TypeError):
                continue

        rubric_clicks, rubric_counts = {}, {}
        for item in logs:
            rub = item.get("rubric")
            topic = item.get("topic_name")
            if not rub or not topic: continue
            rubric_clicks[rub] = rubric_clicks.get(rub, 0) + clicks_by_topic.get(topic, 0)
            rubric_counts[rub] = rubric_counts.get(rub, 0) + 1

        return {
            rub: rubric_clicks[rub] / rubric_counts[rub]
            for rub in rubric_clicks if rubric_counts[rub]
        }
    except Exception as e:
        logger.error(f"Error in get_rubric_ctr_stats: {e}")
    return {}


async def get_top_posts(limit: int = 5, days: int = 30) -> list:
    """Топ постов по кликам за период - для сводки в админ-консоли"""
    if not URL or not KEY or core.session is None: return []
    time_limit = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    try:
        url = f"{URL}/rest/v1/post_history?select=topic_name,clicks,published_at&published_at=gt.{time_limit}&order=clicks.desc&limit={limit}"
        async with core.session.get(url, headers=HEADERS) as r:
            if r.status in (200, 206):
                return await r.json()
    except Exception as e:
        logger.error(f"Error in get_top_posts: {e}")
    return []


async def delete_hidden_promo(code: str):
    """Удаляет осиротевший промокод (шифр не вшился в пост - обещать его нельзя)"""
    if not URL or not KEY or core.session is None: return False
    try:
        # Сначала активации (FK на hidden_promos), затем сам код
        async with core.session.delete(f"{URL}/rest/v1/promo_activations?code=eq.{code}", headers=HEADERS) as r:
            if r.status not in (200, 204):
                logger.error(f"Error deleting activations for promo {code}: {r.status}")
        async with core.session.delete(f"{URL}/rest/v1/hidden_promos?code=eq.{code}", headers=HEADERS) as r:
            if r.status in (200, 204):
                logger.info(f"🗑 Осиротевший промокод {code} удален")
                return True
            logger.error(f"Error deleting hidden promo {code}: {r.status}")
    except Exception as e:
        logger.error(f"Error deleting hidden promo {code}: {e}")
    return False

async def save_hidden_promo(code: str, reward: int, max_uses: int = 10):
    """Сохраняет новый скрытый промокод в базу"""
    if not URL or not KEY or core.session is None: return False
    payload = {
        "code": code,
        "energy_reward": reward,
        "max_uses": max_uses,
        "current_uses": 0
    }
    try:
        async with core.session.post(f"{URL}/rest/v1/hidden_promos", headers=HEADERS, json=payload) as r:
            if r.status in (200, 201, 204):
                logger.success(f"✅ Сохранен скрытый промокод: {code} ({reward} ✨)")
                return True
            else:
                text = await r.text()
                logger.error(f"Ошибка при сохранении промокода {code}: {r.status} - {text}")
    except Exception as e:
        logger.error(f"Error in save_hidden_promo: {e}")
    return False

async def add_community_post(vk_post_id: int, text: str, image_url: str = None) -> bool:
    """Сохраняет свежий пост в Supabase (таблицу community_posts) для Android-приложения"""
    if not URL or not KEY or core.session is None:
        return False

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    payload = {
        "vk_post_id": vk_post_id,
        "text": text,
        "image_url": image_url,
        "published_at": now_iso
    }

    try:
        upsert_headers = HEADERS.copy()
        upsert_headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        url = f"{URL}/rest/v1/community_posts?on_conflict=vk_post_id"
        async with core.session.post(url, headers=upsert_headers, json=payload) as r:
            if r.status in (200, 201, 204):
                logger.success(f"✅ Пост {vk_post_id} успешно сохранен/обновлен в community_posts")
                return True
            else:
                resp_text = await r.text()
                logger.error(f"Ошибка сохранения в community_posts: {r.status} - {resp_text}")
    except Exception as e:
        logger.error(f"Исключение при добавлении в community_posts: {e}")
    return False
