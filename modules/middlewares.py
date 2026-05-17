import json
from loguru import logger
import datetime
import asyncio
from vkbottle import BaseMiddleware
from vkbottle.bot import Message

from cache import check_and_set_throttle_warning, check_throttle
from database import update_user
from modules.utils.ui import delete_bot_message, ghost_edit, get_last_bot_msg

class ThrottleMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        vk_id = self.event.from_id

        # Попытка удалить сообщение пользователя
        if self.event.text:
            asyncio.create_task(delete_bot_message(self.event.ctx_api, self.event.peer_id, cmid=self.event.conversation_message_id))

        # Обновляем дату последней активности
        asyncio.create_task(update_user(vk_id, {"last_active_date": datetime.datetime.now(datetime.timezone.utc).isoformat()}))

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
                if "cmd" in payload or "target" in payload:
                    is_heavy = True
            except json.JSONDecodeError:
                is_heavy = True
        elif self.event.text:
            text = self.event.text.strip()
            if any(text.startswith(emoji) for emoji in ["✦", "💳", "🃏", "📖", "🛰", "🔮", "⚙️", "👤", "🎴", "⚡️", "📢"]):
                is_heavy = True
            # Специальные команды тоже считаем тяжелыми
            if text.lower() in ["начать", "start", "/start", "меню", "профиль"]:
                is_heavy = True

        if is_heavy:
            # Ghost Interface 2.0: Мгновенная реакция
            # Мы сразу редактируем последнее сообщение бота, показывая, что запрос принят
            last_mid = await get_last_bot_msg(vk_id)
            if last_mid:
                asyncio.create_task(ghost_edit(self.event.ctx_api, self.event.peer_id, "✨ Считываю твой запрос из потока...", conversation_message_id=last_mid))

            is_throttled = await check_throttle(vk_id)
            if is_throttled:
                should_warn = await check_and_set_throttle_warning(vk_id)
                if should_warn:
                    try:
                        # Используем ghost_edit вместо answer для предупреждения, чтобы не спамить
                        if last_mid:
                            await ghost_edit(self.event.ctx_api, self.event.peer_id, "⚠️ ТЫ СЛИШКОМ ТОРОПИШЬСЯ, ЭНЕРГИЯ НЕ УСПЕВАЕТ ВОССТАНОВИТЬСЯ", conversation_message_id=last_mid)
                        else:
                            await self.event.answer("ТЫ СЛИШКОМ ТОРОПИШЬСЯ, ЭНЕРГИЯ НЕ УСПЕВАЕТ ВОССТАНОВИТЬСЯ")
                    except Exception as e:
                        logger.error(f"Ошибка предупреждения: {str(e)}")
                self.stop("Throttled")
