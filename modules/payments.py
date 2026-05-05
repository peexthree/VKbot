import math
import asyncio
import json
import random
import re
import datetime
import os
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader, Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType

# Все импорты базы и сервисов — строго здесь
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import (
    bot, generate_premium_pdf, get_fsm_step, upload_local_photo, 
    get_dynamic_keyboard, get_sections_keyboard, get_storefront_keyboard, cover_cache
)
from cache import acquire_lock, release_lock

# Локальные импорты, перенесенные наверх
from modules.services import show_services
from modules.services import show_tariffs
from modules.profile import show_grimoire_page
from modules.profile import view_card_direct
from modules.tarot import process_oracle_final
from loguru import logger

labeler = BotLabeler()

@labeler.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=dict)
async def message_event_handler(event: dict):
    obj = event.get("object", {})
    vk_id = obj.get("user_id")
    peer_id = obj.get("peer_id")
    event_id = obj.get("event_id")
    payload = obj.get("payload", {})

    if not await acquire_lock(vk_id, ttl=2): return
    try:
        if not vk_id or not payload:
            return

        cmd = payload.get("cmd")
        logger.info(f"message_event_handler triggered by vk_id={vk_id}, cmd={cmd}")

        # 1. Сразу отвечаем ВК, чтобы убрать «часики» на кнопке
        try:
            await bot.api.messages.send_message_event_answer(
                event_id=event_id,
                user_id=vk_id,
                peer_id=peer_id
            )
        except Exception as e:
            logger.exception(f"Error answering event: {e}")
            
        # 2. Обработка команд (CALLBACK)
        if cmd == "welcome_bonus":
            user = await get_user(vk_id)
            if not user: return

            if user.get("welcome_bonus_received", False):
                await bot.api.messages.send(peer_id=peer_id, message="Бонус уже получен", random_id=0)
                return

            balance = int(user.get("balance", 0) or 0)
            new_balance = balance + 700
            await update_user(vk_id, {"balance": new_balance, "welcome_bonus_received": True})
            
            await bot.api.messages.send(
                peer_id=peer_id, 
                message="Я подарила тебе 700 Энергии звезд для старта. Этого хватит, чтобы начать свой путь.", 
                random_id=0
            )

            await set_user_state(vk_id, json.dumps({
                "step": "global_cut",
                "target_section": "welcome"
            }))

            kb = {
                "inline": True,
                "buttons": [[{
                    "action": {"type": "callback", "payload": json.dumps({"cmd": "global_cut"}), "label": "✦ СДВИНУТЬ КОЛОДУ"},
                    "color": "secondary"
                }]]
            }
            await bot.api.messages.send(peer_id=peer_id, message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ", keyboard=json.dumps(kb, ensure_ascii=False), random_id=0)

        elif cmd == "use_section":
            target_section = payload.get("key")
            user = await get_user(vk_id)
            if user and target_section:
                purchased = user.get("purchased_sections", {})
                has_access = purchased.get(target_section)
                if target_section in ["sex", "money", "shadow", "final"]:
                    if purchased.get("all") or user.get("has_full_chart"):
                        has_access = True

                if has_access:
                    await set_user_state(vk_id, json.dumps({
                        "step": "global_cut", "target_section": target_section
                    }))
                    kb = Keyboard(inline=True)
                    kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
                    await bot.api.messages.send(peer_id=peer_id, message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json(), random_id=0)
                else:
                    await show_services(vk_id, peer_id, 0) # Fallback if they don't own it

        elif cmd == "main_menu":
            user = await get_user(vk_id)
            kb_json = await get_sections_keyboard(vk_id, user)
            await bot.api.messages.send(peer_id=peer_id, message="ТВОИ ДАННЫЕ В СИСТЕМЕ. КУДА ДВИНЕМСЯ ДАЛЬШЕ?", keyboard=kb_json, random_id=0)

        elif cmd == "service_page":
            idx = payload.get("idx", 0)
            await show_services(vk_id, peer_id, idx, edit_msg_id=obj.get("conversation_message_id"))

        elif cmd == "tariff_page":
            idx = payload.get("idx", 0)
            await show_tariffs(vk_id, peer_id, idx, edit_msg_id=obj.get("conversation_message_id"))

        elif cmd == "buy":
            buy_type = payload.get("type")
            key = payload.get("key")
            
            prices = {
                "sex": 1000, "money": 900, "shadow": 700, "final": 1200, 
                "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500,
                "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900
            }
            
            amount_needed = prices.get(key)
            if not amount_needed: return

            user = await get_user(vk_id)
            if not user: return
            
            balance = int(user.get("balance", 0) or 0)
            
            # Миграция старых бонусов в баланс (если остались)
            bonuses = int(user.get("bonuses", 0) or 0)
            if bonuses > 0:
                balance = (balance * 10) + bonuses
                await update_user(vk_id, {"balance": balance, "bonuses": 0})

            if balance >= amount_needed:
                new_balance = balance - amount_needed
                await update_user(vk_id, {"balance": new_balance})
                
                if buy_type == "service":
                    await process_payment_and_generate(vk_id, key)
                elif buy_type == "tariff":
                    days = 7 if key == "tariff_1" else 30
                    now = datetime.datetime.now(datetime.timezone.utc)
                    new_expires = now + datetime.timedelta(days=days)
                    updates = {"transit_sub_expires_at": new_expires.isoformat()}
                    if key == "tariff_vip":
                        purchased = user.get("purchased_sections", {})
                        for s in ["sex", "money", "shadow", "final"]: purchased[s] = True
                        updates["purchased_sections"] = purchased
                        updates["has_full_chart"] = True
                    await update_user(vk_id, updates)
                    await bot.api.messages.send(
                        peer_id=peer_id, 
                        message=f"ОПЛАТА УСПЕШНА.\n\nТранзит продлен до {new_expires.strftime('%d.%m.%Y %H:%M')}.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {new_balance} Энергии звезд.", 
                        random_id=0
                    )
            else:
                diff_energy = amount_needed - balance
                diff_rubles = math.ceil(diff_energy / 10)
                kb = Keyboard(inline=True)
                kb.add(Callback("ПОПОЛНИТЬ ПРЯМО СЕЙЧАС", payload={"cmd": "pay_refill", "amount": diff_rubles}), color=KeyboardButtonColor.POSITIVE)
                await bot.api.messages.send(
                    peer_id=peer_id, 
                    message=f"Не хватает {diff_energy} Энергии звезд.\n\nПополни свой поток на {diff_rubles} РУБ, чтобы открыть этот раздел.",
                    keyboard=kb.get_json(), random_id=0
                )

        elif cmd == "grimoire_page":
            page = payload.get("page", 0)
            await show_grimoire_page(vk_id, peer_id, page)

        elif cmd == "view_card":
            card_id = str(payload.get("id"))
            await view_card_direct(vk_id, peer_id, card_id)

        elif cmd == "global_cut":
            await bot.api.messages.edit(
                peer_id=peer_id,
                message="СИНХРОНИЗАЦИЯ...",
                conversation_message_id=obj.get("conversation_message_id")
            )
            kb = Keyboard(inline=True)
            for i in range(10):
                if i > 0 and i % 5 == 0: kb.row()
                kb.add(Callback("🎴", payload={"cmd": "global_draw"}), color=KeyboardButtonColor.SECONDARY)
            await bot.api.messages.send(peer_id=peer_id, message="Выбери карту из разложенных:", keyboard=kb.get_json(), random_id=0)

        elif cmd == "global_draw":
            state_dict = await get_fsm_step(vk_id)
            if not state_dict: return
            target_section = state_dict.get("target_section", "")
            partner_name = state_dict.get("partner_name", "")
            partner_date = state_dict.get("partner_date", "")
            await set_user_state(vk_id, "")
            await bot.api.messages.send(peer_id=peer_id, message="Считываю поток...", random_id=0)
            if target_section:
                await execute_generation(vk_id, peer_id, target_section, partner_name, partner_date)

        elif "oracle_card" in payload:
            card_id = payload["oracle_card"]
            state_dict = await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "oracle_draw": return
            drawn_cards = state_dict.get("drawn_cards", [])
            pool = state_dict.get("pool", [])
            if card_id not in drawn_cards: drawn_cards.append(card_id)

            if len(drawn_cards) < 3:
                state_dict["drawn_cards"] = drawn_cards
                await set_user_state(vk_id, json.dumps(state_dict))
                kb = Keyboard(inline=True)
                btn_count = 0
                for c_id in pool:
                    if c_id not in drawn_cards:
                        if btn_count > 0 and btn_count % 5 == 0: kb.row()
                        kb.add(Callback("🎴", payload={"oracle_card": c_id}))
                        btn_count += 1
                await bot.api.messages.edit(
                    peer_id=peer_id, message=f"Выбрано: {len(drawn_cards)}/3...",
                    conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json()
                )
            else:
                await set_user_state(vk_id, "") 
                await bot.api.messages.edit(
                    peer_id=peer_id, message="Выбрано: 3/3. Карты собраны.",
                    conversation_message_id=obj.get("conversation_message_id"), keyboard=Keyboard(inline=True).get_json()
                )
                asyncio.create_task(process_oracle_final(vk_id, state_dict.get("question", ""), drawn_cards))

    finally:
        await release_lock(vk_id)

@labeler.raw_event(GroupEventType.VKPAY_TRANSACTION, dataclass=dict)
async def money_transfer_handler(event: dict):
    try:
        group_id = event.get("group_id")
        if group_id != 219181948: return
        obj = event.get("object", {})
        vk_id = obj.get("from_id")
        amount = obj.get("amount")

        logger.info(f"money_transfer_handler triggered by from_id={vk_id}, amount={amount}")
        tx_key = f"tx_vkpay_{vk_id}_{amount}_{event.get('event_id', 'none')}"
        if not await acquire_lock(tx_key, ttl=3600): return

        if not vk_id or not amount: return
        amount_val = int(amount)
        if amount_val > 1000: amount_val = amount_val // 100

        added_energy = amount_val * 10
        user = await get_user(vk_id)
        if not user: return

        current_balance = int(user.get("balance", 0) or 0)
        new_balance = current_balance + added_energy
        await update_user(vk_id, {"balance": new_balance})

        await bot.api.messages.send(
            peer_id=vk_id,
            message=f"ПОТОК ПОПОЛНЕН! НАЧИСЛЕНО: {added_energy} Энергии звезд.\nНА ТВОЕМ СЧЕТУ: {new_balance} Энергии звезд.",
            random_id=0
        )
    except Exception as e:
        logger.exception(f"Error handling money_transfer: {e}")

async def process_payment_and_generate(vk_id: int, section: str):
    if not await acquire_lock(vk_id): return
    user = await get_user(vk_id)
    if not user: return

    try:
        purchased = user.get("purchased_sections", {})
        if section == "all":
            purchased.update({"sex": True, "money": True, "shadow": True, "final": True})
            await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. Все Врата открыты.", random_id=0)
            # Тут вызываем логику формирования бандла...
        elif section == "oracle":
            purchased["oracle_access"] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, json.dumps({"step": "waiting_oracle_question"}))
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. НАПИШИ СВОЙ ВОПРОС СУДЬБЕ.", random_id=0)
        else:
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.", random_id=0)

        # Стартуем FSM для обрезания колоды
        await set_user_state(vk_id, json.dumps({
            "step": "global_cut", "target_section": section
        }))
        kb = Keyboard(inline=True)
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
        await bot.api.messages.send(peer_id=vk_id, message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json(), random_id=0)

    finally:
        await release_lock(vk_id)

async def execute_generation(vk_id: int, peer_id: int, target_section: str, partner_name: str, partner_date: str):
    # Твоя логика генерации из прошлого файла...
    pass
