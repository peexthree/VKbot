import asyncio
import datetime
import json
import os
import random
from pathlib import Path

import aiofiles
from jinja2 import Environment, FileSystemLoader
from loguru import logger


# Global imports to avoid local import overhead
from vkbottle import Callback, Keyboard, KeyboardButtonColor, PhotoMessageUploader, Text
from database import get_user_state, update_user
from cache import acquire_lock, redis_client, release_lock


# Global cache for cover photo IDs
cover_cache: dict[str, str] = {}

THEATRICAL_PHRASES = [
    "Считываю цифровой след...",
    "Открываю гримуар...",
    "Анализирую векторы вероятности...",
    "Настраиваюсь на ваши вибрации...",
    "Обращаюсь к древним арканам...",
    "Раскладываю карты судьбы...",
    "Запрашиваю ответ у мироздания...",
    "Синхронизирую потоки энергии...",
    "Читаю линии вероятности...",
    "Проникаю в тайны подсознания...",
    "Собираю осколки грядущего...",
    "Вслушиваюсь в шепот звезд...",
    "Приподнимаю завесу тайны...",
    "Сканирую энергетический фон...",
    "Анализирую кармические узлы...",
    "Шарф перемешивается...",
    "Звёзды выстраиваются...",
    "Спрашиваю у духов...",
    "Нити судьбы переплетаются...",
    "Открываю портал в астрал..."
]

SKIN_ASSETS = {
    "Олеся Ивонченко": "o.png",
    "olesya": "o.png",
    "Серьезный Аскет": "as.jpeg",
    "asket": "as.jpeg",
    "Олег Шэпс": "ol.jpeg",
    "Влад Череватов": "2o.jpeg",
    "Виктория Райдес": "v.jpeg",
    "Александр Шеппс": "a.jpeg",
    "Баба Ванга": "ba.jpeg",
    "Григорий Распутин": "r.jpeg",
    "Магистр": "magistr.jpeg"
}
_typing_tasks: dict[int, asyncio.Task] = {}
_typing_msg_ids: dict[int, int] = {}

# Pre-initialize Jinja2 Environment for faster PDF generation
templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
jinja_env = Environment(loader=FileSystemLoader('templates'))
pdf_semaphore = asyncio.Semaphore(1)

ADMIN_ID = int(os.environ.get("ADMIN_ID", 27260796))

async def get_cached_photo(filename: str) -> str | None:
    # 1. Проверяем локальный кэш
    if filename in cover_cache:
        return cover_cache[filename]

    # 2. Проверяем Redis
    try:
        cached_id = await redis_client.get(f"photo:{filename}")
        if cached_id:
            cover_cache[filename] = cached_id
            return cached_id
    except Exception as e:
        logger.error(f"Ошибка чтения фото из Redis: {str(e)}")

    return None


# Batch anchor logic
ANCHOR_BATCH_SIZE = 10
_anchor_batch: list[str] = []

async def flush_anchors(bot_api):
    global _anchor_batch
    if not _anchor_batch:
        return

    try:
        attachments_str = ",".join(_anchor_batch)
        await bot_api.messages.send(
            peer_id=ADMIN_ID,
            message=f"System Anchor Batch ({len(_anchor_batch)} files)",
            attachment=attachments_str,
            random_id=0
        )
    except Exception as e:
        logger.error(f"Ошибка массового якорения фото: {str(e)}")

    _anchor_batch.clear()

async def _anchor_photo_and_cache(bot_api, filename: str, photo_id: str):
    global _anchor_batch

    # Сохраняем в локальный кэш и Redis
    cover_cache[filename] = photo_id
    try:
        await redis_client.set(f"photo:{filename}", photo_id)
    except Exception as e:
        logger.error(f"Ошибка сохранения фото в Redis: {str(e)}")

    _anchor_batch.append(photo_id)
    if len(_anchor_batch) >= ANCHOR_BATCH_SIZE:
        await flush_anchors(bot_api)

async def clear_photo_cache():
    try:
        keys = await redis_client.keys("photo:*")
        if keys:
            await redis_client.delete(*keys)
        cover_cache.clear()
    except Exception as e:
        logger.error(f"Ошибка при очистке кэша фото: {str(e)}")

async def warmup_task():
    if not await acquire_lock("warmup_lock", ttl=3600):
        logger.info("Warmup task already running (lock active).")
        return

    try:
        from modules.bot_init import bot

        # Check if manual sync is active
        warmup_active = await redis_client.get("system_config:warmup_active")
        if not warmup_active or int(warmup_active) != 1:
            logger.info("Синхронизация ассетов ожидала ручного запуска. Режим тишины активен.")
            return

        covers = []
        cards_dir = Path("cards")

        # Программно сканируем всю папку cards и ее подпапки (например, uslugi)
        if cards_dir.exists():
            for root, _, files in os.walk(cards_dir):
                for file in files:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                        full_path = Path(root) / file
                        rel_path = full_path.relative_to(cards_dir)
                        covers.append(str(rel_path).replace("\\", "/"))

        # Для надежности гарантируем наличие списка от 0 до 77, если они существуют
        for i in range(78):
            name = f"{i}.jpeg"
            if name not in covers and (cards_dir / name).exists():
                covers.append(name)

        # Убираем дубликаты и сортируем для предсказуемого порядка
        covers = sorted(list(set(covers)))

        # Audit cache
        missing_covers = []
        for cover in covers:
            if not await get_cached_photo(cover):
                missing_covers.append(cover)

        if not missing_covers:
            logger.info("Предзагрузка (Warmup) отменена: все картинки уже в кэше.")
            await flush_anchors(bot.api)
            # Reset warmup flag after completion
            await redis_client.set("system_config:warmup_active", "0")
            return

        logger.info(f"Запуск умной загрузки (Warmup) для {len(missing_covers)} картинок...")

        # Умная прогрузка: последовательная загрузка с плавающим интервалом для предотвращения блокировок VK
        for cover in missing_covers:
            # Re-check flag to allow mid-way cancellation
            is_active = await redis_client.get("system_config:warmup_active")
            if not is_active or int(is_active) != 1:
                logger.info("Синхронизация ассетов прервана вручную.")
                await flush_anchors(bot.api)
                return

            await upload_local_photo(bot.api, cover)
            # Рандомная пауза от 4 до 7 секунд
            await asyncio.sleep(random.uniform(4.0, 7.0))

        # Сбрасываем оставшиеся якоря
        await flush_anchors(bot.api)

        # Reset warmup flag after completion
        await redis_client.set("system_config:warmup_active", "0")

        logger.info("Предзагрузка (Warmup) картинок успешно завершена.")
    except Exception as e:
        logger.error(f"Ошибка при предзагрузке (Warmup) картинок: {str(e)}")
    finally:
        await release_lock("warmup_lock")

async def upload_local_photo(bot_api, filename: str, peer_id: int | None = None) -> str:
    """Загружает фото локально из папки cards/"""
    if not filename:
        return ""

    # Resolve skin name to filename if needed
    if filename in SKIN_ASSETS:
        filename = SKIN_ASSETS[filename]

    cached = await get_cached_photo(filename)
    if cached:
        return cached

    lock_key = f"upload_lock:{filename}"
    locked = await acquire_lock(lock_key, ttl=30)

    if not locked:
        # Если кто-то уже грузит эту карту
        if peer_id:
            try:
                await bot_api.messages.send(
                    peer_id=peer_id,
                    message="Открываю гримуар...",
                    random_id=0
                )
            except Exception:
                pass

        # Ждем пока загрузится (поллинг)
        for _ in range(15):
            await asyncio.sleep(2)
            cached = await get_cached_photo(filename)
            if cached:
                return cached
        return "" # Таймаут

    try:
        uploader = PhotoMessageUploader(bot_api)
        filepath = os.path.join("cards", filename)

        if not os.path.exists(filepath):
            logger.error(f"Файл не найден: {filepath}")
            return ""

        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()
            if len(data) < 100:
                logger.warning(f"Файл {filename} слишком мал ({len(data)} байт), пропуск загрузки.")
                return ""
            raw_photo_id = await uploader.upload(file_source=data, peer_id=0)
            await _anchor_photo_and_cache(bot_api, filename, raw_photo_id)
            return raw_photo_id
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        return ""
    finally:
        await release_lock(lock_key)

async def check_and_give_daily_bonus(vk_id: int, user: dict | None, peer_id: int):
    """Проверяет и выдает ежедневный бонус (100 Энергии звезд) при отрисовке меню"""
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
            return # Someone already grabbed the lock

        try:
            # Check one more time inside lock to prevent race condition if database state changed
            from database import get_user
            current_user = await get_user(vk_id)
            if not current_user:
                return

            current_last_bonus = current_user.get("last_daily_bonus_date")
            if current_last_bonus:
                try:
                    if now_date <= datetime.date.fromisoformat(current_last_bonus):
                        return
                except ValueError:
                    pass

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

            new_balance = current_balance + 100
            await update_user(vk_id, {
                "balance": new_balance,
                "last_daily_bonus_date": now_date.isoformat(),
                "visit_streak": visit_streak
            })

            # Update local user dict to reflect changes for the current request
            user["balance"] = new_balance
            user["last_daily_bonus_date"] = now_date.isoformat()
            user["visit_streak"] = visit_streak

            try:
                from modules.bot_init import bot
                await bot.api.messages.send(
                    peer_id=peer_id,
                    message=f"🎁 Твой ежедневный дар: +100 Энергии звезд.\nВозвращайся завтра за новой порцией. Твой баланс: {new_balance}.",
                    random_id=0
                )
            except Exception as e:
                logger.error(f"Ошибка: {str(e)}")
        finally:
            await release_lock(lock_key)


def get_main_keyboard() -> str:
    """Генерирует постоянную нижнюю клавиатуру"""
    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("Главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("Профиль", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("Карта дня", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("Услуги", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("Гримуар", payload={"cmd": "grimoire"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_dynamic_keyboard(user: dict | None = None) -> str:
    """Генерирует главную инлайн клавиатуру"""
    keyboard = Keyboard(inline=True)

    keyboard.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Callback("🔮 ГЛУБОКИЕ РАЗБОРЫ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()

    # ←←← ИСПРАВЛЕНИЕ: переводим на callback (Text запрещен в inline)
    keyboard.add(Callback("💳 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Callback("📖 ПУТЕВОДИТЕЛЬ", payload={"cmd": "guide"}), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()


async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    await check_and_give_daily_bonus(vk_id, user, vk_id)

    purchased = user.get("purchased_sections", {}) if user else {}
    has_all = purchased.get("all") or (user and user.get("has_full_chart"))

    kb = Keyboard(inline=True)

    kb.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("🔮 УСЛУГИ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()

    kb.add(Callback("💳 МОЙ ПРОФИЛЬ", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Callback("📖 ПУТЕВОДИТЕЛЬ", payload={"cmd": "guide"}), color=KeyboardButtonColor.SECONDARY)

    # Купленные разделы (остаются callback)
    sections = [
        ("sex", "👄 СЕКСУАЛЬНОСТЬ", purchased.get("sex") or has_all),
        ("money", "💰 БОГАТСТВО", purchased.get("money") or has_all),
        ("shadow", "🌘 ТЕНЬ", purchased.get("shadow") or has_all),
        ("final", "🏁 ПУТЬ", purchased.get("final") or has_all),
        ("antitaro", "👁 АНТИТАРО", purchased.get("antitaro")),
        ("synastry", "👨‍❤️‍👨 СИНАСТРИЯ", purchased.get("synastry"))
    ]

    active_sections = [s for s in sections if s[2]]
    if active_sections:
        buttons_in_row = 0
        for key, label, _ in active_sections:
            if buttons_in_row == 0:
                kb.row()
            kb.add(Callback(label, payload={"cmd": "use_section", "key": key}), color=KeyboardButtonColor.POSITIVE)
            buttons_in_row += 1
            if buttons_in_row == 2:
                buttons_in_row = 0

    return kb.get_json()

async def get_storefront_keyboard(purchased: dict = None) -> str | None:
    """Генерирует резервную инлайн клавиатуру для витрины услуг"""
    if purchased is None:
        purchased = {}
    kb = Keyboard(inline=True)
    kb.add(Callback("👄 Сексуальность", payload={"cmd": "buy", "type": "service", "key": "sex"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Callback("💰 Богатство", payload={"cmd": "buy", "type": "service", "key": "money"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("🌘 Тень", payload={"cmd": "buy", "type": "service", "key": "shadow"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Callback("🏁 Путь", payload={"cmd": "buy", "type": "service", "key": "final"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Callback("👨‍❤️‍👨 Синастрия", payload={"cmd": "buy", "type": "service", "key": "synastry"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("❓ Оракул", payload={"cmd": "buy", "type": "service", "key": "oracle"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Callback("👁 Антитаро", payload={"cmd": "buy", "type": "service", "key": "antitaro"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("👑 Архив (Всё)", payload={"cmd": "buy", "type": "service", "key": "all"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Callback("🏠 В главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

async def get_fsm_step(vk_id: int) -> dict | None:
    data = await get_user_state(vk_id)
    if data:
        try:
            return json.loads(data)
        except Exception:
            return None
    return None

def generate_premium_pdf(
    user_name: str,
    birth_info: str,
    section_name: str,
    text_content: str,
    output_filename: str,
    card_id: str = None,
    advice_content: str = "",
    card_name: str = None,
    card_description: str = None,
    shadow_side: str = "",
    activation_level: int = 100,
    activation_comment: str = "",
    affirmations: str = "",
    next_activation_date: str = "",
    thirty_day_forecast: str = "",
    activation_recommendations: str = "",
    star_code: str = "",
    energy_map: str = "",
    current_date: str = ""
):
    try:
        template = jinja_env.get_template('report.html')

        def safe_br(val):
            if val is None:
                return ""
            if isinstance(val, list):
                val = "\n".join([str(i) for i in val])
            return str(val).replace('\n', '<br>')

        # Подготовка текста
        formatted_text = safe_br(text_content)
        formatted_advice = safe_br(advice_content)

        # Форматирование креативных блоков
        shadow_side = safe_br(shadow_side)
        activation_comment = safe_br(activation_comment)
        affirmations = safe_br(affirmations)
        thirty_day_forecast = safe_br(thirty_day_forecast)
        activation_recommendations = safe_br(activation_recommendations)
        star_code = safe_br(star_code)
        energy_map = safe_br(energy_map)

        # Абсолютный путь к корню проекта (чтобы WeasyPrint находил cards/uslugi/)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # Относительный путь к карте (WeasyPrint будет искать от base_url)
        card_image_path = f"cards/{card_id}.jpeg" if card_id else ""

        html_out = template.render(
            user_name=user_name,
            birth_info=birth_info,
            section_name=section_name,
            text_content=formatted_text,
            advice_content=formatted_advice,
            card_name=card_name or "",
            card_description=card_description or "",
            card_image_path=card_image_path,
            shadow_side=shadow_side,
            activation_level=activation_level,
            activation_comment=activation_comment,
            affirmations=affirmations,
            next_activation_date=next_activation_date,
            thirty_day_forecast=thirty_day_forecast,
            activation_recommendations=activation_recommendations,
            star_code=star_code,
            energy_map=energy_map,
            current_date=current_date
        )

        # Самое важное — base_url
        from weasyprint import HTML
        HTML(string=html_out, base_url=project_root).write_pdf(output_filename)
        
        logger.success(f"PDF успешно создан: {output_filename}")
        return True

    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {str(e)}")
        return False





async def stop_dynamic_typing(peer_id: int) -> int | None:
    global _typing_tasks, _typing_msg_ids
    """Cancels the typing task and returns the message_id that was used for typing."""
    msg_id = _typing_msg_ids.pop(peer_id, None)
    if peer_id in _typing_tasks:
        task = _typing_tasks.pop(peer_id)
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    return msg_id

async def start_dynamic_typing(bot_api, peer_id: int, conversation_message_id: int = None) -> asyncio.Task:
    global _typing_tasks, _typing_msg_ids

    await stop_dynamic_typing(peer_id)

    async def _typing_loop():
        last_phrase = None
        msg_id = None

        # Если нам передали ID сообщения, используем его для редактирования
        if conversation_message_id:
            msg_id = conversation_message_id

        try:
            while True:
                try:
                    available_phrases = [p for p in THEATRICAL_PHRASES if p != last_phrase]
                    phrase = random.choice(available_phrases) if available_phrases else random.choice(THEATRICAL_PHRASES)
                    last_phrase = phrase

                    if msg_id is None:
                        # Используем messages.send и получаем message_id (не conversation_message_id)
                        # vkbottle возвращает message_id
                        resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                        msg_id = resp
                        _typing_msg_ids[peer_id] = msg_id
                    else:
                        # Редактируем. Если это был conversation_message_id, edit сработает
                        # Но vkbottle.edit по умолчанию принимает message_id
                        if conversation_message_id and msg_id == conversation_message_id:
                            await bot_api.messages.edit(peer_id=peer_id, message=phrase, conversation_message_id=msg_id)
                        else:
                            await bot_api.messages.edit(peer_id=peer_id, message=phrase, message_id=msg_id)

                    await bot_api.messages.set_activity(peer_id=peer_id, type="typing")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.debug(f"Typing error: {e}")
                await asyncio.sleep(4) # Ускорим интервал для живости
        finally:
            if peer_id in _typing_tasks and _typing_tasks[peer_id] == asyncio.current_task():
                _typing_tasks.pop(peer_id, None)

    task = asyncio.create_task(_typing_loop())
    _typing_tasks[peer_id] = task
    return task

async def ghost_edit(
    bot_api,
    peer_id: int,
    message: str,
    conversation_message_id: int = None,
    message_id: int = None,
    keyboard: str = None,
    attachment: str = None,
    **kwargs
):
    """
    Универсальный помощник для редактирования сообщений.
    Сначала пробует редактировать по conversation_message_id,
    затем по message_id, если не вышло — отправляет новое.
    """
    try:
        if conversation_message_id:
            await bot_api.messages.edit(
                peer_id=peer_id,
                message=message,
                conversation_message_id=conversation_message_id,
                keyboard=keyboard,
                attachment=attachment,
                **kwargs
            )
            return
        elif message_id:
            await bot_api.messages.edit(
                peer_id=peer_id,
                message=message,
                message_id=message_id,
                keyboard=keyboard,
                attachment=attachment,
                **kwargs
            )
            return
    except Exception as e:
        logger.warning(f"Ghost edit failed (id={conversation_message_id or message_id}): {e}")

    # Fallback to send
    # Важно: vkbottle.messages.send ожидает аргумент message, а не text
    return await bot_api.messages.send(
        peer_id=peer_id,
        message=message,
        keyboard=keyboard,
        attachment=attachment,
        random_id=0,
        **kwargs
    )
