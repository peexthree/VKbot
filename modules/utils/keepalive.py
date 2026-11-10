import asyncio
import os

import aiohttp
from loguru import logger

from cache import get_system_config

KEEPALIVE_CONFIG_KEY = "system_config:keepalive_active"
KEEPALIVE_INTERVAL_SECONDS = 540  # 9 минут
DEFAULT_APP_URL = "https://vkbot-ad64.onrender.com"

_keepalive_task: asyncio.Task | None = None


async def is_keepalive_enabled() -> bool:
    """Возвращает True, если встроенный 9-минутный монитор включен в настройках системы."""
    return (await get_system_config(KEEPALIVE_CONFIG_KEY, default="0")) == "1"


def get_keepalive_ping_url() -> str:
    """Возвращает URL корневого health-эндпоинта приложения для периодического самопинга."""
    app_url = (
        os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("APP_URL")
        or DEFAULT_APP_URL
    )
    return f"{app_url.rstrip('/')}/"


async def render_keepalive_task(initial_delay: float = 60.0) -> None:
    """Фоновый пинг для предотвращения засыпания контейнера на Render Free tier (каждые 9 минут)."""
    global _keepalive_task
    current_task = asyncio.current_task()
    try:
        if initial_delay > 0:
            await asyncio.sleep(initial_delay)
        if not await is_keepalive_enabled():
            logger.info("Render keepalive остановлен: отключен в настройках системы.")
            return

        ping_url = get_keepalive_ping_url()
        logger.info(
            f"Render keepalive task активен: периодический пинг {ping_url} (каждые 9 минут)"
        )
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while True:
                try:
                    await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
                    if not await is_keepalive_enabled():
                        logger.info(
                            "Render keepalive остановлен: отключен в настройках системы."
                        )
                        break
                    async with session.get(ping_url) as resp:
                        logger.debug(f"Render keepalive ping: {resp.status}")
                except asyncio.CancelledError:
                    logger.info("Render keepalive task отменен.")
                    raise
                except Exception as e:
                    logger.debug(f"Render keepalive ping notice: {e}")
    except asyncio.CancelledError:
        logger.info("Render keepalive task остановлен.")
    finally:
        if _keepalive_task is current_task:
            _keepalive_task = None


async def stop_keepalive_task() -> None:
    """Останавливает активную фоновую задачу встроенного keepalive-монитора."""
    global _keepalive_task
    task = _keepalive_task
    _keepalive_task = None
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def sync_keepalive_task(initial_delay: float = 60.0) -> bool:
    """Синхронизирует фоновую задачу keepalive-монитора с системной настройкой.

    По умолчанию монитор выключен (ожидается внешний сервис мониторинга).
    Возвращает True, если задача активна после синхронизации.
    """
    global _keepalive_task
    if await is_keepalive_enabled():
        if _keepalive_task is None or _keepalive_task.done():
            _keepalive_task = asyncio.create_task(
                render_keepalive_task(initial_delay=initial_delay)
            )
        return True

    await stop_keepalive_task()
    logger.info("Render keepalive отключен в настройках системы.")
    return False
