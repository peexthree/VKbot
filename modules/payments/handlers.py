import random
from loguru import logger
from vkbottle import GroupEventType
from vkbottle.bot import BotLabeler
from database import (
    get_user, update_user
)
from modules.bot_init import bot
from modules.utils import ADMIN_ID

labeler = BotLabeler()

@labeler.raw_event(
    [
        GroupEventType.DONUT_SUBSCRIPTION_CREATE,
        GroupEventType.DONUT_SUBSCRIPTION_PROLONGED,
        GroupEventType.DONUT_SUBSCRIPTION_EXPIRED,
        GroupEventType.DONUT_SUBSCRIPTION_CANCELLED
    ],
    dataclass=dict
)
async def donut_handler(event: dict):
    event_type = event.get("type")
    obj = event.get("object", {})
    vk_id = obj.get("user_id")

    if not vk_id: return
    logger.info(f"Donut event {event_type} for user {vk_id}")

    user = await get_user(vk_id)
    if not user: return

    purchased = user.get("purchased_sections", {})

    if event_type in ["donut_subscription_create", "donut_subscription_prolonged"]:
        amount_rub = obj.get("amount", 0)
        energy_added = int(amount_rub) * 10
        # FIX (аудит 2026-11-10): платная операция под локом и атомарным RPC
        # (read-modify-write затирал параллельные списания/пополнения)
        from cache import acquire_lock, release_lock
        from database import add_energy

        if not await acquire_lock(vk_id):
            return
        try:
            purchased["donut_active"] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            new_balance = None
            if await add_energy(vk_id, energy_added):
                _u_after = await get_user(vk_id)
                new_balance = int(_u_after.get("balance", 0) or 0) if _u_after else None
            balance_line = f"Твой баланс: {new_balance} ✨." if new_balance is not None else "Энергия зачислена на баланс."
            action = "оформлена" if event_type == "donut_subscription_create" else "продлена"
            try:
                await bot.api.messages.send(
                    peer_id=vk_id,
                    message=f"🌟 VK Donut подписка успешно {action}!\nТебе начислено {energy_added} Энергии звезд.\n{balance_line}",
                    random_id=random.getrandbits(63)
                )
                await bot.api.messages.send(
                    peer_id=ADMIN_ID,
                    message=f"💰 [DONUT] Пользователь vk.com/id{vk_id} {action} подписку на {amount_rub} RUB (+{energy_added} ✨)",
                    random_id=random.getrandbits(63)
                )
            except Exception as e:
                logger.error(f"Donut notification error: {e}")
        finally:
            await release_lock(vk_id)
    elif event_type in ["donut_subscription_expired", "donut_subscription_cancelled"]:
        purchased["donut_active"] = False
        await update_user(vk_id, {"purchased_sections": purchased})
