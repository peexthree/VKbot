import json

from loguru import logger
import datetime
import asyncio
from vkbottle import BaseMiddleware
from vkbottle.bot import Message

from cache import check_and_set_throttle_warning, check_throttle
from database import update_user, get_user, get_user_state


class ThrottleMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        vk_id = self.event.from_id

        # Проверка на блокировку пользователя
        user_data = await get_user(vk_id)
        if user_data and user_data.get("purchased_sections", {}).get("is_blocked"):
            try:
                await self.event.answer("Вы заблокированы в системе.")
            except:
                pass
            self.stop("Blocked")
            return

        # Обновляем дату последней активности асинхронно
        asyncio.create_task(update_user(vk_id, {"last_active_date": datetime.datetime.now(datetime.timezone.utc).isoformat()}))

        # Трекинг входящего сообщения
        from database import add_event
        metadata = {"has_attachments": bool(self.event.attachments)}
        asyncio.create_task(add_event(vk_id, "message_received", metadata))

        # Check if the message contains payload (inline keyboards often send text+payload or just payload)
        # Or if it starts with heavy commands (we use ✦ prefix for heavy menu buttons or emojis like 🃏)
        # Standard texts might just be chat

        from cache import redis_client
        from modules.utils import ADMIN_ID

        try:
            maintenance_mode = await redis_client.get("system_config:maintenance_mode")
            if maintenance_mode and int(maintenance_mode) == 1 and vk_id != ADMIN_ID:
                try:
                    await self.event.answer("Синдикат в тени. Идет калибровка матрицы.")
                except:
                    pass
                self.stop("Maintenance")
                return
        except Exception as e:
            logger.error(f"Maintenance check error: {str(e)}")

        is_heavy = False
        if self.event.payload:
            try:
                payload = json.loads(self.event.payload)
                # Логируем нажатие кнопки для UX аналитики
                state_dict = await get_user_state(vk_id)
                asyncio.create_task(add_event(vk_id, "ux_interaction", {
                    "payload": payload,
                    "current_state": state_dict,
                    "text": self.event.text
                }))
                if "cmd" in payload or "target" in payload:
                    is_heavy = True
            except json.JSONDecodeError:
                is_heavy = True
        elif self.event.text:
            text = self.event.text.strip()
            # Emojis or specific prefixes used for menu buttons:
            if any(text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "⚙️", "👤", "🎴", "⚡️", "📢"]):
                is_heavy = True

        if is_heavy:
            is_throttled = await check_throttle(vk_id)
            if is_throttled:
                should_warn = await check_and_set_throttle_warning(vk_id)
                if should_warn:
                    try:
                        await self.event.answer("ТЫ СЛИШКОМ ТОРОПИШЬСЯ, ЭНЕРГИЯ НЕ УСПЕВАЕТ ВОССТАНОВИТЬСЯ")
                    except Exception as e:
                        logger.error(f"Ошибка отправки предупреждения о троттлинге: {str(e)}")
                self.stop("Throttled")
