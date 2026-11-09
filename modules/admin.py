import json
import os
import re
import datetime
import asyncio
import random
from vkbottle import Callback, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message

from cache import redis_client, set_fsm_state, get_system_config, set_system_config
from database import get_all_users, get_user, update_user, get_user_count, get_users_paginated
from database.feedbacks import get_unposted_feedbacks
from modules.support import send_feedback_to_chat
from modules.utils import ADMIN_ID, clear_photo_cache, ghost_edit, get_fsm_step
from modules.bot_init import bot

labeler = BotLabeler()

# ==================== НАВИГАЦИЯ ====================

@labeler.message(func=lambda m: m.text and m.text.lower() in ["⚙️ консоль магистра", "админка", "⚙️ консоль"])
@labeler.message(payload={"cmd": "admin_console"})
async def admin_console_handler(message: Message):
    if message.from_id != ADMIN_ID:
        return
    await show_admin_main(message.peer_id)

# ==================== ПАСХАЛКА «ЛАЙН ГОЛОС»: УПРАВЛЕНИЕ СПИСКОМ БЛИЗКИХ ====================

@labeler.message(func=lambda m: m.text and any(
    m.text.lower().startswith(p) for p in ("лайн добавить", "лайн убрать", "лайн список")
))
async def line_god_mode_admin_handler(message: Message):
    if message.from_id != ADMIN_ID:
        return
    from cache import god_mode_allow, god_mode_disallow, god_mode_list

    parts = message.text.strip().lower().split()
    cmd = parts[1] if len(parts) > 1 else ""

    if cmd == "список":
        ids = await god_mode_list()
        if ids:
            text = "🐾 ТЕ, КОГО СЛЫШИТ ЛАЙН:\n" + "\n".join(f"- vk.com/id{i}" for i in ids)
        else:
            text = "🐾 Лайн пока молчит. Список пуст.\n\nФормат: «лайн добавить <vk_id>»"
        await message.answer(text)
        return

    if cmd in ("добавить", "убрать", "+", "-"):
        if len(parts) < 3:
            await message.answer("Формат: «лайн добавить <vk_id>» (только цифры ID)")
            return
        digits = re.sub(r"\D", "", parts[2])
        if not digits:
            await message.answer("Не вижу числового ID. Пример: «лайн добавить 12345678»")
            return
        target_id = int(digits)
        if cmd in ("добавить", "+"):
            ok = await god_mode_allow(target_id)
            status = (
                f"✅ Лайн теперь слышит vk.com/id{target_id}.\n"
                "Повторное «лайн голос» для него = +100 000 ✨ в любой момент."
            )
        else:
            ok = await god_mode_disallow(target_id)
            status = f"🔕 vk.com/id{target_id} убран из списка: «лайн голос» для него теперь тихий."
        if not ok:
            await message.answer("❌ Хранилище недоступно - попробуй через минуту.")
            return
        ids = await god_mode_list()
        extra = ("\n\nВ списке: " + ", ".join(f"vk.com/id{i}" for i in ids)) if ids else "\n\nСписок пуст."
        await message.answer(status + extra)
        return

    await message.answer(
        "🐾 Команды Лайна:\n- «лайн добавить <vk_id>»\n- «лайн убрать <vk_id>»\n- «лайн список»"
    )

async def show_admin_main(peer_id: int, conversation_message_id: int = None):
    """Главная страница консоли"""
    user_count = await get_user_count()

    text = (
        "⚙️ КОНСОЛЬ МАГИСТРА: ГЛАВНАЯ ⚙️\n\n"
        "Добро пожаловать в центр управления матрицей.\n"
        f"👥 Всего адептов: {user_count}\n\n"
        "Выберите раздел для глубокой настройки:"
    )

    kb = Keyboard(inline=True)
    kb.add(Callback("💻 СИСТЕМА", payload={"cmd": "admin_nav", "menu": "system"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("📈 АНАЛИТИКА", payload={"cmd": "admin_nav", "menu": "analytics"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("🧩 UX АНАЛИЗ", payload={"cmd": "admin_nav", "menu": "ux_analytics"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("👥 АДЕПТЫ", payload={"cmd": "admin_nav", "menu": "users"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("📢 ВЕЩАНИЕ", payload={"cmd": "admin_nav", "menu": "broadcast"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("💬 ОТЗЫВЫ", payload={"cmd": "admin_nav", "menu": "feedbacks"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Callback("💎 VIP ХАБ", payload={"cmd": "admin_nav", "menu": "vip"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    # SQL-консоль удалена (аудит 2026-11): RPC exec_sql отозван у anon -
    # он давал произвольный SQL любому владельцу anon-ключа. Работа с
    # данными - через Supabase Dashboard / SQL Editor.
    kb.add(Callback("📜 ЛОГИ", payload={"cmd": "admin_nav", "menu": "logs"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("🏠 ВЫХОД", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_system(peer_id: int, conversation_message_id: int = None, page: int = 0):
    """Раздел системных настроек с пагинацией"""
    warmup_active = ((await get_system_config("system_config:warmup_active", default="0")) == "1")
    maintenance_mode = ((await get_system_config("system_config:maintenance_mode", default="0")) == "1")
    proxy_enabled = ((await get_system_config("system_config:proxy_enabled", default="1")) == "1")
    tag_memory_active = ((await get_system_config("system_config:tag_memory_active", default="1")) == "1")

    try:
        keys = await redis_client.keys("photo:*")
        cache_count = len(keys)
    except:
        cache_count = -1

    text = (
        f"💻 СИСТЕМНЫЕ НАСТРОЙКИ (Стр. {page + 1}/2)\n\n"
        f"🖼 АССЕТОВ В КЭШЕ: {cache_count}\n"
        "--------------------------\n"
    )

    if page == 0:
        text += (
            f"ФОНОВЫЙ ПРОГРЕВ: {'🟢 ВКЛ' if warmup_active else '🔴 ВЫКЛ'}\n"
            "- ПРЕДВАРИТЕЛЬНАЯ ЗАГРУЗКА КАРТ В VK ДЛЯ СКОРОСТИ\n\n"
            f"РЕЖИМ ТЕХ. РАБОТ: {'🔴 АКТИВЕН' if maintenance_mode else '🟢 ВЫКЛ'}\n"
            "- БЛОКИРУЕТ ДОСТУП ВСЕМ, КРОМЕ АДМИНИСТРАТОРА\n\n"
            f"ПРОКСИРОВАНИЕ ИИ: {'🟢 ВКЛ' if proxy_enabled else '🔴 ВЫКЛ'}\n"
            "- ИСПОЛЬЗОВАНИЕ GEMINI_PROXY ДЛЯ ЗАПРОСОВ\n\n"
            f"ТЕГОВАЯ ПАМЯТЬ ИИ: {'🟢 ВКЛ' if tag_memory_active else '🔴 ВЫКЛ'}\n"
            "- СОХРАНЕНИЕ КОНТЕКСТА ПРОШЛЫХ ГАДАНИЙ\n"
        )
    else:
        text += (
            "УПРАВЛЕНИЕ БАЗОЙ И КЭШЕМ:\n"
            "- ВЫПОЛНЕНИЕ SQL ЗАПРОСОВ\n"
            "- ОЧИСТКА ВРЕМЕННЫХ ДАННЫХ И КЭША ФОТО\n"
        )

    kb = Keyboard(inline=True)

    if page == 0:
        # Warmup
        label = "🔴 СТОП ПРОГРЕВ" if warmup_active else "🟢 СТАРТ ПРОГРЕВ"
        kb.add(Callback(label, payload={"cmd": "admin_cmd", "action": "toggle_warmup", "page": page}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

        # Maintenance
        label = "🟢 ВЫКЛ ТЕХРАБОТЫ" if maintenance_mode else "🛠 ВКЛ ТЕХРАБОТЫ"
        kb.add(Callback(label, payload={"cmd": "admin_cmd", "action": "toggle_maintenance", "page": page}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

        # Proxy
        label = "🔴 ВЫКЛ ПРОКСИ" if proxy_enabled else "🟢 ВКЛ ПРОКСИ"
        kb.add(Callback(label, payload={"cmd": "admin_cmd", "action": "toggle_proxy", "page": page}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

        # Memory
        label = "🧠 ВЫКЛ ПАМЯТЬ" if tag_memory_active else "🧠 ВКЛ ПАМЯТЬ"
        kb.add(Callback(label, payload={"cmd": "admin_cmd", "action": "toggle_tag_memory", "page": page}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

        kb.add(Callback("ДАЛЕЕ ➡️", payload={"cmd": "admin_nav", "menu": "system", "page": 1}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
    else:
        # Кнопка SQL удалена (аудит 2026-11): exec_sql отозван у anon
        kb.add(Callback("🧹 ОЧИСТИТЬ REDIS", payload={"cmd": "admin_cmd", "action": "clear_redis", "page": page}), color=KeyboardButtonColor.NEGATIVE)
        kb.row()

        kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "system", "page": 0}), color=KeyboardButtonColor.PRIMARY)
        kb.row()

    kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)

    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_analytics(peer_id: int, conversation_message_id: int = None):
    """Раздел аналитики"""
    from cache import get_ai_rpm
    current_rpm = await get_ai_rpm()

    cached_stats = await redis_client.get("admin:analytics_cache")
    if cached_stats:
        stats = json.loads(cached_stats)
    else:
        users = await get_all_users()
        total_users = len(users)
        now = datetime.datetime.now(datetime.timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        new_today, total_balance, active_today, revenue_est = 0, 0, 0, 0
        purchased_stats = {}
        for u in users:
            total_balance += int(u.get("balance", 0) or 0)
            created_at_str = u.get("created_at")
            if created_at_str:
                try:
                    created_at = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if created_at >= today_start: new_today += 1
                except: pass
            purchased = u.get("purchased_sections", {})
            for key, val in purchased.items():
                if val is True:
                    purchased_stats[key] = purchased_stats.get(key, 0) + 1
                    prices = {"sex": 1000, "money": 900, "shadow": 700, "final": 1200, "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500}
                    revenue_est += prices.get(key, 0)
            last_active = u.get("last_active_date")
            if last_active:
                try:
                    la_date = datetime.datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                    if la_date >= today_start: active_today += 1
                except: pass
        stats = {"total_users": total_users, "new_today": new_today, "active_today": active_today, "total_balance": total_balance, "revenue_est": revenue_est, "purchased_stats": purchased_stats}
        await redis_client.set("admin:analytics_cache", json.dumps(stats), ex=600)

    total_users, new_today, active_today, total_balance, revenue_est, purchased_stats = stats["total_users"], stats["new_today"], stats["active_today"], stats["total_balance"], stats["revenue_est"], stats["purchased_stats"]
    conversion_rate = (new_today / active_today * 100) if active_today > 0 else 0
    stats_text = (
        "📈 АНАЛИТИКА МАТРИЦЫ\n\n"
        f"🤖 ТЕКУЩИЙ AI RPM: {current_rpm}\n"
        f"👥 ВСЕГО АДЕПТОВ: {total_users}\n"
        f"✨ НОВЫХ СЕГОДНЯ: {new_today}\n"
        f"🔥 АКТИВНЫХ СЕГОДНЯ: {active_today}\n"
        f"📊 КОНВЕРСИЯ: {conversion_rate:.1f}%\n"
        f"💰 ЭСТИМЕЙТ ВЫРУЧКИ: ~{revenue_est} RUB\n"
        f"🔋 БАНК ЭНЕРГИИ: {total_balance} ✨\n\n"
        "🔥 ТОП УСЛУГ:\n"
    )
    for key, count in sorted(purchased_stats.items(), key=lambda x: x[1], reverse=True)[:5]:
        stats_text += f"- {key.upper()}: {count}\n"

    # ТОП постов по кликам (аудит 2026-11: данные post_clicks были не видны)
    try:
        from database.autoposter import get_top_posts

        top_posts = await get_top_posts(limit=5, days=30)
        if top_posts:
            stats_text += "\n📰 ТОП ПОСТОВ (30 дней, клики):\n"
            for p in top_posts:
                topic = (p.get("topic_name") or "?")[:40]
                stats_text += f"- {p.get('clicks', 0)} кликов: {topic}\n"
        else:
            stats_text += "\n📰 ТОП ПОСТОВ: данных пока нет\n"
    except Exception as e:
        logger.error(f"Ошибка загрузки топа постов: {e}")

    kb = Keyboard(inline=True).add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, stats_text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_users(peer_id: int, conversation_message_id: int = None, page: int = 0):
    """Раздел управления пользователями с пагинацией (4 на страницу, 2 в ряд)"""
    limit = 4
    offset = page * limit
    users = await get_users_paginated(limit=limit, offset=offset)
    total_users = await get_user_count()
    total_pages = max(1, (total_users + limit - 1) // limit)

    # Корректировка страницы если она вышла за пределы
    if page >= total_pages and total_pages > 0:
        page = total_pages - 1
        offset = page * limit
        users = await get_users_paginated(limit=limit, offset=offset)

    text = (
        "👥 УПРАВЛЕНИЕ АДЕПТАМИ\n\n"
        f"Всего в матрице: {total_users}\n"
        f"Страница: {page + 1} из {total_pages}\n\n"
        "Последние регистрации:"
    )

    kb = Keyboard(inline=True)
    # Выводим по 2 адепта в ряд, чтобы влезть в лимиты VK (макс 6 рядов)
    for i, u in enumerate(users):
        first_name = (u.get("first_name") or "???")[:12]
        vk_id = u.get("vk_id")
        kb.add(Callback(f"👤 {first_name}", payload={"cmd": "admin_user_op", "op": "view_profile", "target": vk_id, "page": page}), color=KeyboardButtonColor.PRIMARY)
        if (i + 1) % 2 == 0 and (i + 1) < len(users):
            kb.row()

    if len(users) > 0:
        kb.row()

    # Пагинация (ряд 3)
    if total_pages > 1:
        if page > 0:
            kb.add(Callback("⬅️ ПРЕД", payload={"cmd": "admin_nav", "menu": "users", "page": page - 1}), color=KeyboardButtonColor.SECONDARY)
        if page < total_pages - 1:
            kb.add(Callback("СЛЕД ➡️", payload={"cmd": "admin_nav", "menu": "users", "page": page + 1}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

    # Ряд 4
    kb.add(Callback("🔍 ПОИСК", payload={"cmd": "admin_cmd", "action": "search_user_start"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    # Ряд 5
    kb.add(Callback("⚡️ МАСС. ЭНЕРГИЯ", payload={"cmd": "admin_cmd", "action": "mass_energy_start"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    # Ряд 6
    kb.add(Callback("⬅️ В МЕНЮ", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)

    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_broadcast(peer_id: int, conversation_message_id: int = None):
    """Раздел рассылки"""
    text = (
        "📢 ПРИЗЫВ СИНДИКАТА (РАССЫЛКА)\n\n"
        "Сообщение будет отправлено всем зарегистрированным адептам.\n"
        "Используйте с осторожностью, чтобы не нарушить баланс матрицы."
    )
    kb = Keyboard(inline=True)
    kb.add(Callback("📝 СОЗДАТЬ ПРИЗЫВ", payload={"cmd": "admin_cmd", "action": "broadcast_start"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🚀 НОВЫЙ АВТОПОСТ", payload={"cmd": "admin_nav", "menu": "autopost_rubrics"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_feedbacks(peer_id: int, conversation_message_id: int = None):
    """Раздел управления отзывами"""
    unposted = await get_unposted_feedbacks(limit=4)
    count = len(unposted)

    text = (
        "💬 УПРАВЛЕНИЕ ОТЗЫВАМИ 💬\n\n"
        f"Неопубликованных отзывов в очереди: {count}/4.\n"
        "При достижении 4 отзывов система автоматически публикует карусель на стену.\n\n"
        "Вы можете принудительно запустить публикацию карусели для тестирования, даже если в очереди меньше 4 отзывов."
    )

    kb = Keyboard(inline=True)
    kb.add(Callback("🚀 ОПУБЛИКОВАТЬ КАРАУСЕЛЬ", payload={"cmd": "admin_cmd", "action": "force_publish_feedbacks"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)

    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_autopost_rubrics(peer_id: int, conversation_message_id: int = None, page: int = 0):
    """Выбор рубрики для автопоста с пагинацией"""
    rubrics = [
        "PROVOCATION", "MYTH_BUST", "BATTLE", "PRACTICUM",
        "NEWS_BREAKDOWN", "STAR_SYNASTRY", "TREND_WATCH",
        "SUPPORT", "FACT", "POLL", "CARD_HISTORY",
        "SACRED_SCIENCE", "DREAM_DECODING", "PALM_CHRONICLES",
        "KARMA_STORY", "CHAKRA_FLOW", "SACRED_RITUAL"
    ]
    limit = 4
    total_pages = (len(rubrics) + limit - 1) // limit
    start = page * limit
    end = start + limit
    current_rubrics = rubrics[start:end]

    text = (
        "🚀 ВЫБОР РУБРИКИ ДЛЯ АВТОПОСТА\n\n"
        "Выберите рубрику, чтобы немедленно сгенерировать и опубликовать пост на стену сообщества.\n"
        f"Страница {page + 1} из {total_pages}"
    )

    kb = Keyboard(inline=True)
    for r in current_rubrics:
        kb.add(Callback(r, payload={"cmd": "admin_cmd", "action": "trigger_autopost", "rubric": r}), color=KeyboardButtonColor.PRIMARY)
        kb.row()

    if total_pages > 1:
        if page > 0:
            kb.add(Callback("⬅️ ПРЕД", payload={"cmd": "admin_nav", "menu": "autopost_rubrics", "page": page - 1}), color=KeyboardButtonColor.SECONDARY)
        if page < total_pages - 1:
            kb.add(Callback("СЛЕД ➡️", payload={"cmd": "admin_nav", "menu": "autopost_rubrics", "page": page + 1}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "broadcast"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_ux_analytics(peer_id: int, conversation_message_id: int = None):
    """Раздел UX-аналитики (Затыки и сбросы)"""
    from database.core import session, URL, HEADERS
    import datetime

    # 1. Поиск "затыков" - пользователи в состоянии дольше 12 часов
    # Мы смотрим на последние ивенты state_transition и ищем тех, у кого нет активности после этого.
    # Но проще посчитать из ивентов ux_interaction и ux_context_reset.

    text = "🧩 UX АНАЛИТИКА: УЗКИЕ МЕСТА\n\n"

    try:
        # Запрос на топ-3 брошенных состояний (где чаще всего делают /start)
        async with session.get(
            f"{URL}/rest/v1/events?action=eq.ux_context_reset&select=metadata",
            headers=HEADERS
        ) as r:
            if r.status == 200:
                data = await r.json()
                abandoned_states = {}
                for item in data:
                    metadata = item.get("metadata", {})
                    abandoned_state_data = metadata.get("abandoned_state", {})
                    if isinstance(abandoned_state_data, dict):
                        state = abandoned_state_data.get("step", "unknown")
                    else:
                        state = str(abandoned_state_data)
                    abandoned_states[state] = abandoned_states.get(state, 0) + 1

                sorted_abandoned = sorted(abandoned_states.items(), key=lambda x: x[1], reverse=True)[:3]

                text += "📉 ТОП-3 ТОЧКИ СБРОСА (Context Reset):\n"
                if sorted_abandoned:
                    for state, count in sorted_abandoned:
                        text += f"- {state}: {count} раз\n"
                else:
                    text += "- Данных пока нет\n"
            else:
                text += "❌ Ошибка получения данных о сбросах\n"
    except Exception as e:
        text += f"❌ Ошибка UX: {e}\n"

    text += "\n⏳ ТОП-3 ЗАТЫКА (>12ч в одном state):\n"
    try:
        # Получаем последние переходы
        async with session.get(
            f"{URL}/rest/v1/events?action=eq.state_transition&order=created_at.desc&limit=100",
            headers=HEADERS
        ) as r:
            if r.status == 200:
                transitions = await r.json()
                now = datetime.datetime.now(datetime.timezone.utc)
                stuck_states = {}
                processed_users = set()

                for t in transitions:
                    uid = t.get("user_id")
                    if uid in processed_users: continue
                    processed_users.add(uid)

                    created_at = datetime.datetime.fromisoformat(t.get("created_at").replace('Z', '+00:00'))
                    if (now - created_at).total_seconds() > 12 * 3600:
                        state_data = t.get("metadata", {}).get("new_state", "unknown")
                        if isinstance(state_data, str) and state_data.startswith("{"):
                            try: state = json.loads(state_data).get("step", "unknown")
                            except: state = "unknown"
                        else: state = str(state_data)

                        stuck_states[state] = stuck_states.get(state, 0) + 1

                sorted_stuck = sorted(stuck_states.items(), key=lambda x: x[1], reverse=True)[:3]
                if sorted_stuck:
                    for state, count in sorted_stuck:
                        text += f"- {state}: {count} чел.\n"
                else:
                    text += "- Застрявших адептов не обнаружено\n"
            else:
                text += "❌ Ошибка получения данных о затыках\n"
    except Exception as e:
        text += f"❌ Ошибка анализа: {e}\n"

    kb = Keyboard(inline=True)
    kb.add(Callback("🔄 ОБНОВИТЬ", payload={"cmd": "admin_nav", "menu": "ux_analytics"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)

    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_vip(peer_id: int, conversation_message_id: int = None):
    """Раздел управления VIP-клиентами"""
    users = await get_all_users()
    vip_users = [u for u in users if u.get("has_full_chart") or (u.get("balance", 0) or 0) > 5000]
    text = (
        "💎 VIP ХАБ: УПРАВЛЕНИЕ ЭЛИТОЙ 💎\n\n"
        f"Количество VIP-адептов: {len(vip_users)}\n"
        "--------------------------\n"
        "VIP-статус имеют те, у кого открыт полный архив или баланс > 5000 ✨.\n\n"
        "Выберите действие:"
    )
    kb = Keyboard(inline=True)
    kb.add(Callback("👑 СПИСОК VIP", payload={"cmd": "admin_cmd", "action": "list_vips"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("🎁 ВЫДАТЬ VIP", payload={"cmd": "admin_cmd", "action": "search_user_start"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

async def show_admin_logs(peer_id: int, conversation_message_id: int = None):
    """Просмотр последних логов"""
    log_dir, log_text = "logs", ""
    try:
        files = [f for f in os.listdir(log_dir) if f.startswith("bot_") and f.endswith(".log")]
        if not files: log_text = "Логи не найдены."
        else:
            latest_file = sorted(files)[-1]
            with open(os.path.join(log_dir, latest_file), "r", encoding="utf-8") as f:
                lines = f.readlines()
                log_text = "".join(lines[-5:])
    except Exception as e: log_text = f"Ошибка при чтении логов: {e}"

    # Ensure log_text is not too long to avoid VKAPIError_914 (Message is too long)
    # The limit is normally ~4096, but we leave room for the header.
    if len(log_text) > 3500:
        log_text = log_text[-3500:]

    text = f"📜 ПОСЛЕДНИЕ СОБЫТИЯ:\n\n{log_text}"
    kb = Keyboard(inline=True)
    kb.add(Callback("🔄 ОБНОВИТЬ", payload={"cmd": "admin_nav", "menu": "logs"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "main"}), color=KeyboardButtonColor.PRIMARY)
    await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)


# ==================== ОБРАБОТКА КОМАНД ====================

async def process_admin_cmd(vk_id: int, peer_id: int, payload: dict, conversation_message_id: int = None):
    if vk_id != ADMIN_ID: return
    action, nav_menu = payload.get("action"), payload.get("menu")
    page = payload.get("page", 0)
    if payload.get("cmd") == "admin_nav":
        if nav_menu == "main": await show_admin_main(peer_id, conversation_message_id)
        elif nav_menu == "system": await show_admin_system(peer_id, conversation_message_id, page=page)
        elif nav_menu == "analytics": await show_admin_analytics(peer_id, conversation_message_id)
        elif nav_menu == "users": await show_admin_users(peer_id, conversation_message_id, page=page)
        elif nav_menu == "broadcast": await show_admin_broadcast(peer_id, conversation_message_id)
        elif nav_menu == "autopost_rubrics": await show_admin_autopost_rubrics(peer_id, conversation_message_id, page=page)
        elif nav_menu == "logs": await show_admin_logs(peer_id, conversation_message_id)
        elif nav_menu == "vip": await show_admin_vip(peer_id, conversation_message_id)
        elif nav_menu == "feedbacks": await show_admin_feedbacks(peer_id, conversation_message_id)
        elif nav_menu == "ux_analytics": await show_admin_ux_analytics(peer_id, conversation_message_id)
        return
    if action == "force_publish_feedbacks":
        await bot.api.messages.send(peer_id=peer_id, message="⏳ Начинаю принудительную публикацию карусели отзывов...", random_id=random.getrandbits(63))
        success, msg = await send_feedback_to_chat(vk_id=vk_id, section="", rating=5, comment_text="", force=True)
        if success:
            await bot.api.messages.send(peer_id=peer_id, message=f"✅ {msg}", random_id=random.getrandbits(63))
        else:
            await bot.api.messages.send(peer_id=peer_id, message=f"❌ {msg}", random_id=random.getrandbits(63))
        await show_admin_feedbacks(peer_id, conversation_message_id)
    elif action == "toggle_warmup":
        c = await get_system_config("system_config:warmup_active", default="0")
        nv = 0 if c == "1" else 1
        await set_system_config("system_config:warmup_active", nv)
        if nv == 1:
            from modules.utils import warmup_task
            asyncio.create_task(warmup_task())
        await show_admin_system(peer_id, conversation_message_id, page=page)
    elif action == "toggle_maintenance":
        c = await get_system_config("system_config:maintenance_mode", default="0")
        nv = 0 if c == "1" else 1
        await set_system_config("system_config:maintenance_mode", nv)
        await show_admin_system(peer_id, conversation_message_id, page=page)
    elif action == "toggle_proxy":
        c = await get_system_config("system_config:proxy_enabled", default="1")
        nv = 0 if c == "1" else 1
        await set_system_config("system_config:proxy_enabled", nv)
        await show_admin_system(peer_id, conversation_message_id, page=page)
    elif action == "toggle_tag_memory":
        c = await get_system_config("system_config:tag_memory_active", default="1")
        nv = 0 if c == "1" else 1
        await set_system_config("system_config:tag_memory_active", nv)
        await show_admin_system(peer_id, conversation_message_id, page=page)
    elif action == "list_vips":
        users = await get_all_users()
        vips = [u for u in users if u.get("has_full_chart") or (u.get("balance", 0) or 0) > 5000]
        text = "💎 СПИСОК VIP-АДЕПТОВ:\n\n"
        for u in vips[:20]: text += f"- ID: {u['vk_id']} | {u.get('balance', 0)} ✨ | {'FULL' if u.get('has_full_chart') else 'RICH'}\n"
        if not vips: text += "VIP-адепты не обнаружены."
        kb = Keyboard(inline=True).add(Callback("⬅️ НАЗАД", payload={"cmd": "admin_nav", "menu": "vip"}), color=KeyboardButtonColor.PRIMARY)
        await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)
    elif action == "clear_redis":
        await clear_photo_cache()
        await bot.api.messages.send(peer_id=peer_id, message="Кэш фото в Redis очищен.", random_id=random.getrandbits(63))
        await show_admin_system(peer_id, conversation_message_id, page=page)
    elif action == "search_user_start":
        await set_fsm_state(vk_id, json.dumps({"step": "admin_user_search", "conv_id": conversation_message_id}))
        await bot.api.messages.send(peer_id=peer_id, message="Введите VK ID адепта для поиска:", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_nav", "menu": "users"})).get_json(), random_id=random.getrandbits(63))
    elif action == "broadcast_start":
        await set_fsm_state(vk_id, json.dumps({"step": "admin_broadcast_message", "conv_id": conversation_message_id}))
        await bot.api.messages.send(peer_id=peer_id, message="📝 Введите текст призыва (рассылки).\n\nОн будет отправлен всем адептам Синдиката.", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_nav", "menu": "broadcast"})).get_json(), random_id=random.getrandbits(63))
    elif action == "broadcast_confirm":
        bt = await redis_client.get(f"admin:broadcast_text:{vk_id}")
        if not bt:
            await bot.api.messages.send(peer_id=peer_id, message="❌ Текст призыва утерян. Начните заново.", random_id=random.getrandbits(63))
            await show_admin_broadcast(peer_id, conversation_message_id)
            return
        bt = bt.decode('utf-8') if isinstance(bt, bytes) else bt
        await bot.api.messages.send(peer_id=peer_id, message="🚀 Запуск трансмиссии...", random_id=random.getrandbits(63))
        users = await get_all_users()
        success = 0
        for u in users:
            try:
                await bot.api.messages.send(peer_id=u["vk_id"], message=f"📢 ПРИЗЫВ СИНДИКАТА 📢\n\n{bt}", random_id=random.getrandbits(63))
                success += 1
                await asyncio.sleep(0.05)
            except: pass
        await bot.api.messages.send(peer_id=peer_id, message=f"✅ Рассылка завершена. Доставлено: {success}/{len(users)}", random_id=random.getrandbits(63))
        await show_admin_broadcast(peer_id, conversation_message_id)
    elif action == "trigger_autopost":
        rubric = payload.get("rubric")
        label = f" ({rubric})" if rubric else ""
        await bot.api.messages.send(peer_id=peer_id, message=f"🔮 Запуск генерации нового поста{label}...", random_id=random.getrandbits(63))
        from modules.autoposter import post_to_vk
        asyncio.create_task(post_to_vk(forced_rubric=rubric))
        await bot.api.messages.send(peer_id=peer_id, message=f"✅ Задача на автопостинг{label} поставлена в очередь.", random_id=random.getrandbits(63))
        await show_admin_broadcast(peer_id, conversation_message_id)
    elif action == "sql_exec_start":
        # SQL-консоль удалена (аудит 2026-11): exec_sql отозван у anon-ключа -
        # произвольный SQL из чата был RCE-каналом в прод-БД.
        await bot.api.messages.send(peer_id=peer_id, message="🔒 SQL-консоль отключена по результатам аудита безопасности. Работа с данными - через Supabase Dashboard.", random_id=random.getrandbits(63))
        await show_admin_main(peer_id, conversation_message_id)
    elif action == "mass_energy_start":
        await set_fsm_state(vk_id, json.dumps({"step": "admin_energy_target", "conv_id": conversation_message_id}))
        await bot.api.messages.send(peer_id=peer_id, message="Введите ID и количество энергии через пробел (например: 12345 500):", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_nav", "menu": "users"})).get_json(), random_id=random.getrandbits(63))
    elif payload.get("cmd") == "admin_user_op":
        op, target = payload.get("op"), payload.get("target")
        if op == "view_profile":
            user = await get_user(target)
            if not user:
                await bot.api.messages.send(peer_id=peer_id, message="Адепт не найден.", random_id=random.getrandbits(63))
                return
            purchased, skins, has_full = user.get("purchased_sections", {}), user.get("purchased_skins", []), user.get("has_full_chart", False)
            current_page = payload.get("page", 0)

            # Расширенная статистика
            stats_clicks = purchased.get("stats_clicks", 0)
            stats_rub = purchased.get("stats_total_rubles", 0)
            last_active = user.get("last_active_date", "???")

            is_blocked = purchased.get("is_blocked", False)
            text = (
                f"👤 ПРОФИЛЬ АДЕПТА: {target} {'[🔴 ЗАБЛОКИРОВАН]' if is_blocked else ''}\n"
                f"Имя: {user.get('first_name', '???')}\n"
                f"Баланс: {user.get('balance', 0)} ✨\n"
                f"Потрачено: {stats_rub} RUB\n"
                f"Активность: {stats_clicks} кликов\n"
                f"Скины: {', '.join(skins) if skins else 'нет'}\n"
                f"Услуги: {sum(1 for k, v in purchased.items() if v is True and k not in ['first_name', 'sex_val', 'conversion_step'])}\n"
                f"Full Chart: {'✅' if has_full else '❌'}\n"
                f"Зарегистрирован: {user.get('created_at', '???')}\n"
                f"Последний вход: {last_active}"
            )
            kb = Keyboard(inline=True)
            kb.add(Callback("⚡️ БАЛАНС", payload={"cmd": "admin_user_op", "op": "edit_balance", "target": target, "page": current_page}), color=KeyboardButtonColor.PRIMARY)
            kb.add(Callback("✉️ НАПИСАТЬ", payload={"cmd": "admin_user_op", "op": "direct_msg_start", "target": target, "page": current_page}), color=KeyboardButtonColor.PRIMARY)
            kb.row()
            kb.add(Callback("👑 FULL UNLOCK", payload={"cmd": "admin_user_op", "op": "full_unlock", "target": target, "page": current_page}), color=KeyboardButtonColor.POSITIVE)
            kb.row()
            kb.add(Callback("🎁 КАРТА", payload={"cmd": "admin_user_op", "op": "give_card_start", "target": target, "page": current_page}), color=KeyboardButtonColor.SECONDARY)
            kb.row()
            # Кнопки Блокировки и Удаления
            block_label = "🟢 РАЗБЛОКИРОВАТЬ" if is_blocked else "🔴 ЗАБЛОКИРОВАТЬ"
            kb.add(Callback(block_label, payload={"cmd": "admin_user_op", "op": "toggle_block", "target": target, "page": current_page}), color=KeyboardButtonColor.SECONDARY)
            kb.add(Callback("🗑 УДАЛИТЬ", payload={"cmd": "admin_user_op", "op": "delete_user", "target": target, "page": current_page}), color=KeyboardButtonColor.NEGATIVE)
            kb.row()
            kb.add(Callback("⬅️ К СПИСКУ", payload={"cmd": "admin_nav", "menu": "users", "page": current_page}), color=KeyboardButtonColor.SECONDARY)
            await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

        elif op == "direct_msg_start":
            curr_page = payload.get("page", 0)
            await set_fsm_state(vk_id, json.dumps({"step": "admin_user_direct_message", "target": target, "conv_id": conversation_message_id, "page": curr_page}))
            await bot.api.messages.send(peer_id=peer_id, message=f"📝 Введите сообщение для адепта {target}:", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_user_op", "op": "view_profile", "target": target, "page": curr_page})).get_json(), random_id=random.getrandbits(63))

        elif op == "edit_balance":
            curr_page = payload.get("page", 0)
            await set_fsm_state(vk_id, json.dumps({"step": "admin_user_edit_balance", "target": target, "conv_id": conversation_message_id, "page": curr_page}))
            await bot.api.messages.send(peer_id=peer_id, message=f"Введите НОВОЕ значение баланса для {target}:", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_user_op", "op": "view_profile", "target": target, "page": curr_page})).get_json(), random_id=random.getrandbits(63))
        elif op == "full_unlock":
            user = await get_user(target)
            if user:
                curr_page = payload.get("page", 0)
                p = user.get("purchased_sections", {})
                for s in ["sex", "money", "shadow", "final", "synastry", "antitaro"]: p[s] = True
                await update_user(target, {"purchased_sections": p, "has_full_chart": True})
                await bot.api.messages.send(peer_id=peer_id, message=f"✅ Все услуги разблокированы для {target}", random_id=random.getrandbits(63))
                await bot.api.messages.send(peer_id=target, message="🌟 Магистр даровал вам полный доступ ко всем тайнам Синдиката!", random_id=random.getrandbits(63))
                await show_admin_users(peer_id, conversation_message_id, page=curr_page)
        elif op == "give_card_start":
            curr_page = payload.get("page", 0)
            await set_fsm_state(vk_id, json.dumps({"step": "admin_user_give_card", "target": target, "conv_id": conversation_message_id, "page": curr_page}))
            await bot.api.messages.send(peer_id=peer_id, message=f"Введите ID карты (0-77) для выдачи адепту {target}:", keyboard=Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "admin_user_op", "op": "view_profile", "target": target, "page": curr_page})).get_json(), random_id=random.getrandbits(63))

        elif op == "toggle_block":
            user = await get_user(target)
            if user:
                curr_page = payload.get("page", 0)
                p = user.get("purchased_sections", {})
                new_state = not p.get("is_blocked", False)
                p["is_blocked"] = new_state
                await update_user(target, {"purchased_sections": p})
                status_msg = "заблокирован" if new_state else "разблокирован"
                await bot.api.messages.send(peer_id=peer_id, message=f"✅ Адепт {target} {status_msg}.", random_id=random.getrandbits(63))
                await process_admin_cmd(vk_id, peer_id, {"cmd": "admin_user_op", "op": "view_profile", "target": target, "page": curr_page}, conversation_message_id=conversation_message_id)

        elif op == "delete_user":
            curr_page = payload.get("page", 0)
            text = f"⚠️ ВЫ УВЕРЕНЫ, ЧТО ХОТИТЕ ПОЛНОСТЬЮ УДАЛИТЬ АДЕПТА {target}?\n\nЭто действие необратимо и сотрет все его данные из матрицы."
            kb = Keyboard(inline=True)
            kb.add(Callback("🔥 ДА, УДАЛИТЬ", payload={"cmd": "admin_user_op", "op": "confirm_delete", "target": target, "page": curr_page}), color=KeyboardButtonColor.NEGATIVE)
            kb.row()
            kb.add(Callback("⬅️ ОТМЕНА", payload={"cmd": "admin_user_op", "op": "view_profile", "target": target, "page": curr_page}), color=KeyboardButtonColor.PRIMARY)
            await ghost_edit(bot.api, peer_id, text, keyboard=kb.get_json(), conversation_message_id=conversation_message_id)

        elif op == "confirm_delete":
            from database import delete_user
            success = await delete_user(target)
            curr_page = payload.get("page", 0)
            if success:
                await bot.api.messages.send(peer_id=peer_id, message=f"✅ Адепт {target} навсегда удален из матрицы.", random_id=random.getrandbits(63))
                await show_admin_users(peer_id, conversation_message_id, page=curr_page)
            else:
                await bot.api.messages.send(peer_id=peer_id, message=f"❌ Ошибка при удалении адепта {target}.", random_id=random.getrandbits(63))
                await process_admin_cmd(vk_id, peer_id, {"cmd": "admin_user_op", "op": "view_profile", "target": target, "page": curr_page}, conversation_message_id=conversation_message_id)

async def _is_admin_fsm(message: Message) -> bool:
    if message.from_id != ADMIN_ID: return False
    fsm_data = await get_fsm_step(message.from_id)
    if not fsm_data: return False
    return fsm_data.get("step") in ["admin_user_search", "admin_broadcast_message", "admin_energy_target", "admin_user_edit_balance", "admin_user_give_card", "admin_user_direct_message", "admin_sql_exec"]

@labeler.message(func=_is_admin_fsm)
async def admin_fsm_handler(message: Message):
    fsm_data = await get_fsm_step(message.from_id)
    step, vk_id, conv_id = fsm_data.get("step"), message.from_id, fsm_data.get("conv_id")
    if message.text.lower() == "отмена":
        await set_fsm_state(vk_id, "")
        await show_admin_main(message.peer_id, conv_id)
        return
    if step == "admin_user_search":
        try:
            target_id = int(message.text.strip())
            await set_fsm_state(vk_id, "")
            await process_admin_cmd(vk_id, message.peer_id, {"cmd": "admin_user_op", "op": "view_profile", "target": target_id}, conversation_message_id=conv_id)
        except ValueError: await message.answer("Введите корректный числовой ID.")
    elif step == "admin_user_edit_balance":
        try:
            target_id, new_bal = fsm_data.get("target"), int(message.text.strip())
            curr_page = fsm_data.get("page", 0)
            await update_user(target_id, {"balance": new_bal})
            await set_fsm_state(vk_id, "")
            await message.answer(f"Баланс пользователя {target_id} изменен на {new_bal} ✨")
            await show_admin_users(message.peer_id, conv_id, page=curr_page)
        except: await message.answer("Введите число.")
    elif step == "admin_user_give_card":
        try:
            target_id, card_id = fsm_data.get("target"), str(int(message.text.strip()))
            curr_page = fsm_data.get("page", 0)
            user = await get_user(target_id)
            if not user: return
            unlocked = user.get("unlocked_cards", {})
            from cards_data import get_card_data
            card_data = get_card_data(card_id)
            if not card_data:
                await message.answer("Такой карты не существует.")
                return
            unlocked[card_id] = f"{card_data.get('name')} - ДАР МАГИСТРА"
            await update_user(target_id, {"unlocked_cards": unlocked})
            await set_fsm_state(vk_id, "")
            await message.answer(f"✅ Карта {card_id} выдана адепту {target_id}")
            await bot.api.messages.send(peer_id=target_id, message=f"🎁 Магистр Синдиката даровал вам новую карту в Гримуар: {card_data.get('name')}!", random_id=random.getrandbits(63))
            await show_admin_users(message.peer_id, conv_id, page=curr_page)
        except: await message.answer("Введите число ID карты (0-77).")
    elif step == "admin_energy_target":
        parts = message.text.strip().split()
        if len(parts) != 2:
            await message.answer("Формат: ID КОЛИЧЕСТВО")
            return
        try:
            target_id, amount = int(parts[0]), int(parts[1])
            target_user = await get_user(target_id)
            if not target_user:
                await message.answer("Пользователь не найден.")
                return
            new_balance = int(target_user.get("balance", 0) or 0) + amount
            await update_user(target_id, {"balance": new_balance})
            await set_fsm_state(vk_id, "")
            await message.answer(f"Зачислено {amount} ✨ пользователю {target_id}. Итого: {new_balance}")
            try: await bot.api.messages.send(peer_id=target_id, message=f"⚡️ Магистр даровал вам {amount} Энергии звезд!\nВаш баланс: {new_balance}", random_id=random.getrandbits(63))
            except: pass
            await show_admin_users(message.peer_id, conv_id)
        except: await message.answer("Ошибка в числах.")
    elif step == "admin_user_direct_message":
        try:
            target_id, text = fsm_data.get("target"), message.text.strip()
            curr_page = fsm_data.get("page", 0)
            await bot.api.messages.send(peer_id=target_id, message=f"💬 СООБЩЕНИЕ ОТ МАГИСТРА:\n\n{text}", random_id=random.getrandbits(63))
            await set_fsm_state(vk_id, "")
            await message.answer(f"✅ Сообщение успешно отправлено адепту {target_id}")
            await process_admin_cmd(vk_id, message.peer_id, {"cmd": "admin_user_op", "op": "view_profile", "target": target_id, "page": curr_page}, conversation_message_id=conv_id)
        except Exception as e:
            await message.answer(f"❌ Ошибка при отправке: {e}")
    elif step == "admin_broadcast_message":
        text = message.text.strip()
        await set_fsm_state(vk_id, "")
        await redis_client.set(f"admin:broadcast_text:{vk_id}", text, ex=3600)
        kb = Keyboard(inline=True)
        kb.add(Callback("✅ ПОДТВЕРДИТЬ", payload={"cmd": "admin_cmd", "action": "broadcast_confirm"}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("❌ ОТМЕНА", payload={"cmd": "admin_nav", "menu": "broadcast"}), color=KeyboardButtonColor.NEGATIVE)
        await ghost_edit(bot.api, message.peer_id, f"ПРЕВЬЮ ПРИЗЫВА:\n\n📢 ПРИЗЫВ СИНДИКАТА 📢\n\n{text}\n\nОтправить всем адептам?", keyboard=kb.get_json(), conversation_message_id=conv_id)
    elif step == "admin_sql_exec":
        # Защитная ветка: стейт мог остаться с прошлой версии - мягко выходим
        await set_fsm_state(vk_id, "")
        await message.answer("🔒 SQL-консоль отключена по результатам аудита безопасности.")
        await show_admin_main(vk_id, conv_id)

async def show_admin_console(peer_id: int, conversation_message_id: int = None):
    await show_admin_main(peer_id, conversation_message_id=conversation_message_id)
