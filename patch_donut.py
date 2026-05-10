with open("modules/payments.py", "r") as f:
    content = f.read()
donut_handler = """@labeler.raw_event(
    [
        GroupEventType.DONUT_SUBSCRIPTION_CREATE,
        GroupEventType.DONUT_SUBSCRIPTION_PROLONGED,
        GroupEventType.DONUT_SUBSCRIPTION_EXPIRED,
        GroupEventType.DONUT_SUBSCRIPTION_CANCELLED
    ],
    dataclass=dict
)
async def donut_handler(event: dict):
    from database import get_user, update_user
    from modules.bot_init import bot

    event_type = event.get("type")
    obj = event.get("object", {})
    vk_id = obj.get("user_id")

    if not vk_id:
        return

    logger.info(f"Donut event {event_type} for user {vk_id}")

    user = await get_user(vk_id)
    if not user:
        return

    purchased = user.get("purchased_sections", {})
    balance = int(user.get("balance", 0) or 0)

    if event_type in ["donut_subscription_create", "donut_subscription_prolonged"]:
        amount_rub = obj.get("amount", 0)
        energy_added = int(amount_rub) * 10
        new_balance = balance + energy_added
        purchased["donut_active"] = True

        await update_user(vk_id, {"balance": new_balance, "purchased_sections": purchased})

        action = "оформлена" if event_type == "donut_subscription_create" else "продлена"
        try:
            await bot.api.messages.send(
                peer_id=vk_id,
                message=f"🌟 VK Donut подписка успешно {action}!\\nТебе начислено {energy_added} Энергии звезд.\\nТвой баланс: {new_balance} ✨.",
                random_id=0
            )
            # Notify admin
            from modules.utils import ADMIN_ID
            await bot.api.messages.send(
                peer_id=ADMIN_ID,
                message=f"💰 [DONUT] Пользователь vk.com/id{vk_id} {action} подписку на {amount_rub} RUB (+{energy_added} ✨)",
                random_id=0
            )
        except Exception as e:
            logger.error(f"Donut notification error: {e}")

    elif event_type in ["donut_subscription_expired", "donut_subscription_cancelled"]:
        purchased["donut_active"] = False
        await update_user(vk_id, {"purchased_sections": purchased})

        action = "истекла" if event_type == "donut_subscription_expired" else "отменена"
        try:
            await bot.api.messages.send(
                peer_id=vk_id,
                message=f"🥀 Твоя VK Donut подписка {action}. Ты больше не получаешь регулярную Энергию звезд.",
                random_id=0
            )
        except Exception:
            pass
"""
if "def donut_handler" not in content:
    content += "\n" + donut_handler
with open("modules/payments.py", "w") as f:
    f.write(content)
