from vkbottle import BaseMiddleware
from vkbottle.bot import Message
from cache import check_throttle
import json

class ThrottleMiddleware(BaseMiddleware[Message]):
    async def pre(self):
        vk_id = self.event.from_id

        # Check if the message contains payload (inline keyboards often send text+payload or just payload)
        # Or if it starts with heavy commands (we use ✦ prefix for heavy menu buttons or emojis like 🃏)
        # Standard texts might just be chat
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
            # Emojis or specific prefixes used for menu buttons:
            if text.startswith("✦") or text.startswith("🃏") or text.startswith("📖") or text.startswith("🛰") or text.startswith("🔮"):
                is_heavy = True

        if is_heavy:
            is_throttled = await check_throttle(vk_id)
            if is_throttled:
                self.stop("Throttled")
