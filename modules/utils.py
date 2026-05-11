import asyncio
import datetime
import json
import os

import aiofiles
from jinja2 import Environment, FileSystemLoader
from loguru import logger


# Global imports to avoid local import overhead
from vkbottle import Callback, Keyboard, KeyboardButtonColor, PhotoMessageUploader, Text
from database import get_user_state, update_user


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

# Pre-initialize Jinja2 Environment for faster PDF generation
templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
jinja_env = Environment(loader=FileSystemLoader('templates'))
pdf_semaphore = asyncio.Semaphore(1)

from cache import acquire_lock, redis_client, release_lock

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
        import os
        import random
        from pathlib import Path

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
        current_balance = int(user.get("balance", 0) or 0)
        visit_streak = user.get("visit_streak", 0)

        if last_bonus_date_str:
            try:
                last_bonus_date = datetime.date.fromisoformat(last_bonus_date_str)
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
        try:
            from modules.bot_init import bot
            await bot.api.messages.send(
                peer_id=peer_id,
                message=f"🎁 Твой ежедневный дар: +100 Энергии звезд.\nВозвращайся завтра за новой порцией. Твой баланс: {new_balance}.",
                random_id=0
            )
        except Exception as e:
            logger.error(f"Ошибка: {str(e)}")


def get_main_keyboard() -> str:
    """Генерирует постоянную нижнюю клавиатуру"""
    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("Главное меню", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text("Профиль", payload={"cmd": "profile_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("Карта дня", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text("Услуги", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("Гримуар", payload={"cmd": "grimoire"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()

def get_dynamic_keyboard(user: dict | None = None) -> str:
    """Генерирует главную инлайн клавиатуру"""
    keyboard = Keyboard(inline=True)

    keyboard.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Callback("🔮 ГЛУБОКИЕ РАЗБОРЫ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()

    # ←←← ИСПРАВЛЕНИЕ: переводим на text, чтобы срабатывали text-хендлеры
    keyboard.add(Text("💳 МОЙ ПРОФИЛЬ"), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text("📖 ПУТЕВОДИТЕЛЬ"), color=KeyboardButtonColor.SECONDARY)

    return keyboard.get_json()


async def get_sections_keyboard(vk_id: int, user: dict | None) -> str:
    await check_and_give_daily_bonus(vk_id, user, vk_id)

    purchased = user.get("purchased_sections", {}) if user else {}
    has_all = purchased.get("all") or (user and user.get("has_full_chart"))

    # Используем обычный Keyboard (inline), но кнопки Профиль и Путеводитель — text
    kb = Keyboard(inline=True)

    kb.add(Callback("🃏 КАРТА ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
    kb.add(Callback("🔮 УСЛУГИ", payload={"cmd": "services_menu"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()

    # ←←← ИСПРАВЛЕНИЕ: text-кнопки
    kb.add(Text("💳 МОЙ ПРОФИЛЬ"), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("📖 ПУТЕВОДИТЕЛЬ"), color=KeyboardButtonColor.SECONDARY)
    kb.row()

    # Купленные разделы (остаются callback)
    if purchased.get("sex") or has_all:
        kb.add(Callback("👄 СЕКСУАЛЬНОСТЬ", payload={"cmd": "use_section", "key": "sex"}), color=KeyboardButtonColor.POSITIVE)
    if purchased.get("money") or has_all:
        kb.add(Callback("💰 БОГАТСТВО", payload={"cmd": "use_section", "key": "money"}), color=KeyboardButtonColor.POSITIVE)
    if purchased.get("shadow") or has_all:
        kb.add(Callback("🌘 ТЕНЬ", payload={"cmd": "use_section", "key": "shadow"}), color=KeyboardButtonColor.POSITIVE)
    if purchased.get("final") or has_all:
        kb.add(Callback("🏁 ПУТЬ", payload={"cmd": "use_section", "key": "final"}), color=KeyboardButtonColor.POSITIVE)
    if purchased.get("antitaro"):
        kb.add(Callback("👁 АНТИТАРО", payload={"cmd": "use_section", "key": "antitaro"}), color=KeyboardButtonColor.POSITIVE)
    if purchased.get("synastry"):
        kb.add(Callback("👨‍❤️‍👨 СИНАСТРИЯ", payload={"cmd": "use_section", "key": "synastry"}), color=KeyboardButtonColor.POSITIVE)

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
    card_description: str = None
):
    try:
        template = jinja_env.get_template('report.html')
        
        # Подготовка текста
        formatted_text = text_content.replace('\n', '<br>')
        formatted_advice = advice_content.replace('\n', '<br>') if advice_content else ""

        # Абсолютный путь к корню проекта (чтобы WeasyPrint находил cards/uslugi/)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        html_out = template.render(
            user_name=user_name,
            birth_info=birth_info,
            section_name=section_name,
            text_content=formatted_text,
            advice_content=formatted_advice,
            card_name=card_name,         
            card_description=card_description,  
            card_image_path=f"file://{os.path.abspath(f'cards/{card_id}.jpeg')}" if card_id and os.path.exists(f'cards/{card_id}.jpeg') else ""
        )

        # Самое важное — base_url
        from weasyprint import HTML
        HTML(string=html_out, base_url=project_root).write_pdf(output_filename)
        
        logger.info(f"✅ PDF успешно создан: {output_filename}")
        return True

    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {str(e)}")
        return False

def stop_dynamic_typing(peer_id: int):
    global _typing_tasks
    """Cancels the typing task for a given peer_id if it exists."""
    if peer_id in _typing_tasks:
        task = _typing_tasks.pop(peer_id)
        if not task.done():
            task.cancel()

async def start_dynamic_typing(peer_id: int, bot_api) -> asyncio.Task:
    global _typing_tasks
    import random

    stop_dynamic_typing(peer_id)

    async def _typing_loop():
        # Keep track of the last phrase to avoid visual duplication
        last_phrase = None
        # We need a message to edit rather than sending new messages to prevent chat spam
        msg_id = None

        while True:
            try:
                available_phrases = [p for p in THEATRICAL_PHRASES if p != last_phrase]
                phrase = random.choice(available_phrases) if available_phrases else random.choice(THEATRICAL_PHRASES)
                last_phrase = phrase

                if msg_id is None:
                    resp = await bot_api.messages.send(peer_id=peer_id, message=phrase, random_id=0)
                    msg_id = resp
                else:
                    await bot_api.messages.edit(peer_id=peer_id, message=phrase, message_id=msg_id)
                await bot_api.messages.set_activity(peer_id=peer_id, type="typing")
            except Exception:
                pass
            await asyncio.sleep(10)

    task = asyncio.create_task(_typing_loop())
    _typing_tasks[peer_id] = task
    return task

class MockMsg:
    def __init__(self, from_id, peer_id):
        self.from_id = from_id
        self.peer_id = peer_id
    async def answer(self, message: str = None, **kwargs):
        from modules.bot_init import bot
        # extract attachment, keyboard, etc from kwargs
        if 'attachment' in kwargs:
            await bot.api.messages.send(peer_id=self.peer_id, random_id=0, message=message, attachment=kwargs['attachment'], keyboard=kwargs.get('keyboard'))
        else:
            await bot.api.messages.send(peer_id=self.peer_id, random_id=0, message=message, keyboard=kwargs.get('keyboard'))
