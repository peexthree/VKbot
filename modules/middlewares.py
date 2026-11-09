import json

from loguru import logger
import datetime
import asyncio
import time
from vkbottle import BaseMiddleware
from vkbottle.bot import Message

from cache import check_and_set_throttle_warning, check_throttle, get_system_config
from database import update_user, get_user, get_user_state

_last_active_sent: dict[int, float] = {}


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

        # Проверка регистрации для предотвращения обхода онбординга
        is_registered = user_data.get("is_registered") if user_data else False
        if user_data and is_registered is None:
            # Обратная совместимость для старых записей и мок-тестов
            is_registered = True

        if not is_registered:
            is_start = False
            if self.event.text:
                text_lower = self.event.text.lower().strip()
                if text_lower in ["начать", "start", "/start", "консоль", "console"]:
                    is_start = True
            if self.event.payload:
                try:
                    payload = json.loads(self.event.payload)
                    if payload.get("command") == "start" or payload.get("cmd") == "start":
                        is_start = True
                except:
                    pass

            is_reset = False
            if self.event.text:
                text_lower = self.event.text.lower().strip()
                if text_lower in {"сброс", "reset", "обнулить", "начать заново"}:
                    is_reset = True

            is_onboarding_fsm = False
            state_raw = await get_user_state(vk_id)
            if state_raw:
                try:
                    state_dict = json.loads(state_raw)
                    if isinstance(state_dict, dict):
                        step = state_dict.get("step", "")
                        if step in ["waiting_birth_date", "waiting_birth_time", "waiting_birth_city", "confirm_data"] or step.startswith("waiting_birth"):
                            is_onboarding_fsm = True
                except json.JSONDecodeError:
                    if state_raw in ["onboarding_skin_selection"]:
                        is_onboarding_fsm = True

            is_allowed_payload = False
            if self.event.payload:
                try:
                    payload = json.loads(self.event.payload)
                    cmd = payload.get("cmd")
                    allowed_onboarding_cmds = [
                        "choose_onboarding_skin",
                        "confirm_registration",
                        "edit_onboarding_data",
                        "skip_birth_time",
                        "skin_page",
                        "skins_page",
                        "skin_quest",
                        "set_skin",
                        "buy_skin",
                    ]
                    if cmd in allowed_onboarding_cmds:
                        is_allowed_payload = True
                except:
                    pass

            if not (is_start or is_reset or is_onboarding_fsm or is_allowed_payload):
                try:
                    await self.event.answer("🌌 Пожалуйста, заверши настройку своего профиля!")
                except:
                    pass
                from modules.registration import start_handler
                await start_handler(self.event, skip_lock=True)
                self.stop("Redirected to onboarding")
                return

        # Обновляем дату последней активности асинхронно, но не чаще
        # 1 раза в минуту на юзера (in-memory троттлинг: 0 сетевых запросов к Upstash)
        now_ts = time.time()
        if now_ts - _last_active_sent.get(vk_id, 0.0) > 60.0:
            _last_active_sent[vk_id] = now_ts
            asyncio.create_task(update_user(vk_id, {"last_active_date": datetime.datetime.now(datetime.timezone.utc).isoformat()}))

        # Трекинг входящего сообщения
        from database import add_event
        metadata = {"has_attachments": bool(self.event.attachments)}
        asyncio.create_task(add_event(vk_id, "message_received", metadata))

        # Check if the message contains payload (inline keyboards often send text+payload or just payload)
        # Or if it starts with heavy commands (we use ✦ prefix for heavy menu buttons or emojis like 🃏)
        # Standard texts might just be chat

        from modules.utils import ADMIN_ID

        try:
            m_val = await get_system_config("system_config:maintenance_mode", default="0")
            is_maintenance = (m_val == "1")
            if is_maintenance and vk_id != ADMIN_ID:
                try:
                    await self.event.answer("Синдикат в тени. Идет калибровка матрицы.")
                except Exception:
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
