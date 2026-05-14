from loguru import logger
from vkbottle import GroupEventType
from vkbottle.bot import BotLabeler
from database import (
    check_and_save_transaction, get_user, update_user
)
from modules.bot_init import bot
from cache import acquire_lock
from modules.utils import ADMIN_ID

labeler = BotLabeler()

@labeler.raw_event(GroupEventType.VKPAY_TRANSACTION, dataclass=dict)
async def money_transfer_handler(event: dict):
    try:
        group_id = event.get("group_id")
        if group_id != 219181948: return
        obj = event.get("object", {})
        vk_id = obj.get("from_id")
        amount = obj.get("amount")

        logger.info(f"money_transfer_handler triggered by from_id={vk_id}, amount={amount}")

        event_id = event.get('event_id') or str(obj.get('date', 'none'))
        tx_key = f"tx_vkpay_{vk_id}_{amount}_{event_id}"

        if not await acquire_lock(tx_key, ttl=3600): return

        if not vk_id or not amount: return

        amount_rubles = int(amount) // 1000

        if not await check_and_save_transaction(tx_key, vk_id, amount_rubles):
            logger.warning(f"money_transfer_handler: duplicate or invalid transaction {tx_key} rejected")
            return

        added_energy = amount_rubles * 10
        user = await get_user(vk_id)
        if not user: return

        current_balance = int(user.get("balance", 0) or 0)
        new_balance = current_balance + added_energy
        await update_user(vk_id, {"balance": new_balance})

        await bot.api.messages.send(
            peer_id=vk_id,
            message=f"БАЛАНС УСПЕШНО ПОПОЛНЕН.\nНАЧИСЛЕНО: {added_energy} Энергии звезд.\nНА ТВОЕМ СЧЕТУ: {new_balance} Энергии звезд.",
            random_id=0
        )
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")

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
                message=f"🌟 VK Donut подписка успешно {action}!\nТебе начислено {energy_added} Энергии звезд.\nТвой баланс: {new_balance} ✨.",
                random_id=0
            )
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
        except Exception: pass
