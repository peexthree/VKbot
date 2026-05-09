import asyncio
import datetime
import json
import math
import os
import random
import re
from typing import Any

from loguru import logger
from vkbottle import Callback, DocMessagesUploader, Keyboard, KeyboardButtonColor
from vkbottle.bot import BotLabeler, Message
from vkbottle.tools.dev.keyboard.action import VKPay

from ai_service import generate_section
from cache import acquire_lock, check_throttle, release_lock
from cards_data import get_card_data
from database import check_and_save_transaction, get_user, set_user_state, update_user
from modules.bot_init import bot
from modules.profile import view_card_direct
from modules.services import show_services, show_tariffs
from modules.tarot import card_of_day_logic, process_oracle_final
from modules.utils import (
    SKIN_ASSETS,
    generate_premium_pdf,
    get_fsm_step,
    get_sections_keyboard,
    pdf_semaphore,
    start_dynamic_typing,
    stop_dynamic_typing,
    upload_local_photo,
)

labeler = BotLabeler()


# ====================== УНИВЕРСАЛЬНЫЙ ХЕЛПЕР ======================
async def send_or_edit(peer_id: int, text: str, keyboard=None, attachment=None, conv_msg_id=None, message_id=None):
    """Единая функция для редактирования или отправки сообщения"""
    try:
        if conv_msg_id:
            await bot.api.messages.edit(
                peer_id=peer_id,
                conversation_message_id=conv_msg_id,
                message=text,
                keyboard=keyboard,
                attachment=attachment
            )
        elif message_id:
            await bot.api.messages.edit(
                peer_id=peer_id,
                message_id=message_id,
                message=text,
                keyboard=keyboard,
                attachment=attachment
            )
        else:
            await bot.api.messages.send(
                peer_id=peer_id,
                message=text,
                keyboard=keyboard,
                attachment=attachment,
                random_id=0
            )
    except Exception:
        # Fallback
        await bot.api.messages.send(
            peer_id=peer_id,
            message=text,
            keyboard=keyboard,
            attachment=attachment,
            random_id=0
        )


# ====================== ОСНОВНОЙ ХЕНДЛЕР CALLBACK ======================
@labeler.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=dict)
async def message_event_handler(event: dict):
    """Центральный обработчик всех inline-кнопок и событий"""
    obj = event.get("object", {})
    vk_id = obj.get("user_id")
    peer_id = obj.get("peer_id")
    event_id = obj.get("event_id")
    payload = obj.get("payload", {})
    conv_msg_id = obj.get("conversation_message_id")
    msg_id = obj.get("message_id")

    if not vk_id or not payload:
        return
    if await check_throttle(vk_id):
        return
    if not await acquire_lock(vk_id, ttl=3):
        return

    try:
        # Сразу подтверждаем событие VK (убираем "часики")
        try:
            await bot.api.messages.send_message_event_answer(
                event_id=event_id, user_id=vk_id, peer_id=peer_id
            )
        except Exception:
            pass

        cmd = payload.get("cmd")

        # ==================== АДМИН ====================
        if cmd == "admin_cmd":
            from modules.admin import process_admin_cmd
            await process_admin_cmd(vk_id, peer_id, payload)
            return

        # ==================== ПРОФИЛЬ ====================
        if cmd == "profile_action":
            from modules.profile import profile_action_handler
            await profile_action_handler(event)
            return

        # ==================== УСЛУГИ И ТАРИФЫ ====================
        if cmd == "services_menu":
            await show_services(vk_id, peer_id, 0)
        elif cmd == "tariffs":
            await show_tariffs(vk_id, peer_id, 0)
        elif cmd == "service_page":
            idx = payload.get("idx", 0)
            await show_services(vk_id, peer_id, idx, edit_msg_id=conv_msg_id)
        elif cmd == "tariff_page":
            idx = payload.get("idx", 0)
            await show_tariffs(vk_id, peer_id, idx, edit_msg_id=conv_msg_id)

        # ==================== КАРТА ДНЯ ====================
        elif cmd in ["card_of_day", "card_of_day_menu"]:
            await card_of_day_logic(vk_id, peer_id, message_id=msg_id, conversation_message_id=conv_msg_id)

        # ==================== ГРИМУАР ====================
        elif cmd == "grimoire_page":
            page = payload.get("page", 0)
            from modules.profile import show_grimoire_page
            await show_grimoire_page(vk_id, peer_id, page)
        elif cmd == "view_card":
            card_id = str(payload.get("id"))
            await view_card_direct(vk_id, peer_id, card_id)

        # ==================== ПОКУПКА ====================
        elif cmd == "buy":
            await handle_buy(vk_id, peer_id, payload, conv_msg_id, msg_id)

        # ==================== PDF ====================
        elif cmd == "gen_pdf":
            await handle_gen_pdf(vk_id, peer_id, payload, conv_msg_id, msg_id)

        # ==================== GLOBAL CUT / DRAW ====================
        elif cmd == "global_cut":
            await handle_global_cut(vk_id, peer_id, payload, conv_msg_id)
        elif cmd == "global_draw":
            await handle_global_draw(vk_id, peer_id, payload, conv_msg_id)

        # ==================== ОРАКУЛ ====================
        elif "oracle_card" in payload:
            card_id = payload.get("oracle_card")
            await handle_oracle_card(vk_id, peer_id, card_id, conv_msg_id)

    finally:
        await release_lock(vk_id)




# ====================== ПОКУПКА ======================
async def handle_buy(vk_id: int, peer_id: int, payload: dict, conv_msg_id=None, msg_id=None):
    """Основная логика покупки услуги или тарифа"""
    if not await acquire_lock(f"buy:{vk_id}", ttl=15):
        return

    try:
        await start_dynamic_typing(bot.api, peer_id)

        buy_type = payload.get("type")
        key = payload.get("key")

        prices = {
            "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
            "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500,
            "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900
        }
        amount_needed = prices.get(key)
        if not amount_needed:
            return

        user = await get_user(vk_id)
        if not user:
            return

        balance = int(user.get("balance", 0) or 0)

        # Миграция старых бонусов (если остались)
        bonuses = int(user.get("bonuses", 0) or 0)
        if bonuses > 0:
            balance = balance * 10 + bonuses
            await update_user(vk_id, {"balance": balance, "bonuses": 0})

        if balance >= amount_needed:
            new_balance = balance - amount_needed
            await update_user(vk_id, {"balance": new_balance})

            if buy_type == "service":
                await process_payment_and_generate(vk_id, key, conv_msg_id or msg_id)
            elif buy_type == "tariff":
                await process_tariff_purchase(vk_id, key, new_balance, peer_id, conv_msg_id or msg_id)
        else:
            diff_energy = amount_needed - balance
            diff_rubles = math.ceil(diff_energy / 10)

            kb = Keyboard(inline=True)
            kb.add(VKPay(hash=f"action=pay-to-group&group_id=219181948&amount={diff_rubles}"))
            kb.row()
            kb.add(Callback("🎁 ПОЗВАТЬ ДРУГА (+500 ✨)", payload={"cmd": "get_referral"}), color=KeyboardButtonColor.POSITIVE)

            await send_or_edit(
                peer_id=peer_id,
                text=f"🛑 НЕДОСТАТОЧНО ЭНЕРГИИ.\n"
                     f"Твой баланс: {balance} ✨\n"
                     f"Нужно: {amount_needed} ✨\n\n"
                     f"Оплати {diff_rubles} RUB или позови друга.",
                keyboard=kb.get_json(),
                conv_msg_id=conv_msg_id,
                message_id=msg_id
            )

    finally:
        stop_dynamic_typing(peer_id)
        await release_lock(f"buy:{vk_id}")


async def process_tariff_purchase(vk_id: int, key: str, new_balance: int, peer_id: int, edit_msg_id: int | None = None):
    """Обработка покупки тарифа"""
    days = 7 if key == "tariff_1" else 30
    now = datetime.datetime.now(datetime.timezone.utc)
    new_expires = now + datetime.timedelta(days=days)

    updates: dict[str, Any] = {"transit_sub_expires_at": new_expires.isoformat()}

    if key == "tariff_vip":
        user = await get_user(vk_id)
        purchased = user.get("purchased_sections", {})
        for s in ["sex", "money", "shadow", "final"]:
            purchased[s] = True
        updates["purchased_sections"] = purchased
        updates["has_full_chart"] = True

    await update_user(vk_id, updates)

    await send_or_edit(
        peer_id=peer_id,
        text=f"ОПЛАТА УСПЕШНА.\n\n"
             f"Транзит продлен до {new_expires.strftime('%d.%m.%Y %H:%M')}.\n"
             f"ТВОЙ ТЕКУЩИЙ БАЛАНС: {new_balance} Энергии звезд.",
        keyboard=Keyboard(inline=True).get_json(),
        message_id=edit_msg_id
    )

# ====================== ОБРАБОТКА ПОКУПКИ УСЛУГИ ======================
async def process_payment_and_generate(vk_id: int, section: str, edit_msg_id: int | None = None):
    """Активация купленной услуги + переход к шагу обрезания колоды"""
    if not await acquire_lock(f"process_payment:{vk_id}", ttl=300):
        return

    try:
        await start_dynamic_typing(bot.api, vk_id)

        user = await get_user(vk_id)
        if not user:
            return

        purchased = user.get("purchased_sections", {}) or {}

        if section == "all":
            for s in ["sex", "money", "shadow", "final"]:
                purchased[s] = True
            await update_user(vk_id, {
                "purchased_sections": purchased,
                "has_full_chart": True
            })
            prefix = "УСЛУГА АКТИВИРОВАНА. Все Врата открыты.\n\n"
        elif section in ["oracle", "antitaro"]:
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            prefix = "УСЛУГА АКТИВИРОВАНА.\n\n"
        else:
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            prefix = "УСЛУГА АКТИВИРОВАНА.\n\n"

        # Переход к выбору карты
        await set_user_state(vk_id, json.dumps({
            "step": "global_cut",
            "target_section": section
        }))

        kb = Keyboard(inline=True)
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)

        await send_or_edit(
            peer_id=vk_id,
            text=prefix + "ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.",
            keyboard=kb.get_json(),
            message_id=edit_msg_id
        )

    finally:
        stop_dynamic_typing(vk_id)
        await release_lock(f"process_payment:{vk_id}")


# ====================== GLOBAL CUT / DRAW ======================
async def handle_global_cut(vk_id: int, peer_id: int, payload: dict, conv_msg_id=None):
    """Шаг выбора карты из колоды (10 карт)"""
    if not await acquire_lock(f"global_cut:{vk_id}", ttl=30):
        return

    try:
        await start_dynamic_typing(bot.api, peer_id)

        target = payload.get("target")
        if target:
            await set_user_state(vk_id, json.dumps({
                "step": "global_cut",
                "target_section": target
            }))

        kb = Keyboard(inline=True)
        for i in range(10):
            if i > 0 and i % 5 == 0:
                kb.row()
            kb.add(Callback("🎴", payload={"cmd": "global_draw"}), color=KeyboardButtonColor.SECONDARY)

        await send_or_edit(
            peer_id=peer_id,
            text="Выбери карту из разложенных:",
            keyboard=kb.get_json(),
            conv_msg_id=conv_msg_id
        )
    finally:
        await release_lock(f"global_cut:{vk_id}")


async def handle_global_draw(vk_id: int, peer_id: int, payload: dict, conv_msg_id=None):
    """Обработка выбора одной карты из 10"""
    if not await acquire_lock(f"global_draw:{vk_id}", ttl=30):
        return
    try:
        await start_dynamic_typing(bot.api, peer_id)

        card_id = str(random.randint(0, 77))
        card_data = get_card_data(card_id)

        user = await get_user(vk_id)
        if not user:
            return

        unlocked = user.get("unlocked_cards", {}) or {}
        if card_id not in unlocked:
            unlocked[card_id] = f"{card_data.get('name', 'Карта')} — {card_data.get('subtitle', 'Новое знание')}"

        await update_user(vk_id, {
            "unlocked_cards": unlocked,
            "total_cards_received": user.get("total_cards_received", 0) + 1
        })

        state = await get_fsm_step(vk_id)
        target_section = state.get("target_section", "") if state else ""

        await execute_generation(
            vk_id=vk_id,
            peer_id=peer_id,
            target_section=target_section,
            partner_name=state.get("partner_name", "") if state else "",
            partner_date=state.get("partner_date", "") if state else "",
            card_id=card_id,
            card_data=card_data
        )
finally:
        await release_lock(f"global_draw:{vk_id}")
# ====================== ГЕНЕРАЦИЯ РАЗБОРА ======================
async def execute_generation(vk_id: int, peer_id: int, target_section: str, partner_name: str = "", partner_date: str = "", card_id: str = None, card_data: dict = None):
    """Основная генерация разбора после выбора карты"""
    if not await acquire_lock(f"execute_gen:{vk_id}", ttl=300):
        return

    try:
        user = await get_user(vk_id)
        if not user:
            return

        await start_dynamic_typing(bot.api, peer_id)

        active_skin = user.get("active_skin", "olesya")
        tags = user.get("tags", [])

        res_text = await generate_section(
            target_section,
            user.get("birth_date"),
            user.get("birth_time"),
            user.get("birth_city"),
            core_profile=user.get("core_profile", ""),
            first_name=user.get("purchased_sections", {}).get("first_name", ""),
            sex=user.get("sex_val", 0),
            partner_name=partner_name,
            partner_date=partner_date,
            skin=active_skin,
            card_id=card_id,
            card_data=card_data,
            tags=tags
        )

        if res_text:
            # Очищаем технические метки ID_ТАРО
            display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", res_text).strip()

            # Сохраняем текст для возможного PDF
            await update_user(vk_id, {"latest_reading_text": display_text})

            # Сохраняем теги в фоне
            asyncio.create_task(background_save_tags(vk_id, res_text))

            # Добавляем кнопку PDF в клавиатуру
            kb_str = await get_sections_keyboard(vk_id, user)
            kb_dict = json.loads(kb_str)
            kb_dict.setdefault("buttons", []).append([{
                "action": {
                    "type": "callback",
                    "payload": json.dumps({"cmd": "gen_pdf", "section": target_section, "card": card_id}),
                    "label": "📄 СГЕНЕРИРОВАТЬ PDF"
                },
                "color": "secondary"
            }])

            await send_or_edit(
                peer_id=peer_id,
                text=display_text,
                keyboard=json.dumps(kb_dict, ensure_ascii=False)
            )
        else:
            await handle_generation_failure(vk_id, peer_id, target_section)

    finally:
        stop_dynamic_typing(peer_id)
        await release_lock(f"execute_gen:{vk_id}")


async def background_save_tags(vk_id: int, text: str):
    """Фоновая задача сохранения тегов"""
    try:
        from ai_service import extract_tags
        new_tags = await extract_tags(text)
        if new_tags:
            await update_user(vk_id, {"tags": new_tags})
    except Exception as e:
        logger.error(f"background_save_tags error for {vk_id}: {e}")


async def handle_generation_failure(vk_id: int, peer_id: int, target_section: str):
    """Возврат энергии при ошибке генерации"""
    prices = {
        "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
        "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500
    }
    price = prices.get(target_section, 0)

    if price > 0:
        user = await get_user(vk_id)
        if user:
            new_balance = int(user.get("balance", 0) or 0) + price
            await update_user(vk_id, {"balance": new_balance})

    await send_or_edit(
        peer_id=peer_id,
        text="Кажется, сегодня звёзды немного запутались. Энергия возвращена на баланс. Попробуй ещё раз."
    )


# ====================== PDF ======================
async def handle_gen_pdf(vk_id: int, peer_id: int, payload: dict, conv_msg_id=None, msg_id=None):
    """Генерация и отправка PDF-файла разбора"""
    if not await acquire_lock(f"pdf_gen:{vk_id}", ttl=60):
        return

    try:
        await start_dynamic_typing(bot.api, peer_id)

        section = payload.get("section", "report")
        card_id = payload.get("card", "")

        user = await get_user(vk_id)
        if not user:
            return

        latest_text = user.get("latest_reading_text", "")
        if not latest_text:
            await send_or_edit(
                peer_id,
                "Текст разбора не найден. Сгенерируйте разбор заново.",
                conv_msg_id=conv_msg_id,
                message_id=msg_id
            )
            return

        await send_or_edit(
            peer_id,
            "Создаю PDF-файл, подожди секунду...",
            conv_msg_id=conv_msg_id,
            message_id=msg_id
        )

        pdf_name = f"report_{vk_id}_{section}.pdf"
        b_info = f"{user.get('birth_date')} {user.get('birth_time')} {user.get('birth_city')}"
        first_name = user.get("purchased_sections", {}).get("first_name", "Странник")

        async with pdf_semaphore:
            success = await asyncio.to_thread(
                generate_premium_pdf,
                first_name,
                b_info,
                section.upper(),
                latest_text,
                pdf_name,
                card_id
            )

        if success and os.path.exists(pdf_name):
            doc = await DocMessagesUploader(bot.api).upload(
                title=f"{section}.pdf",
                file_source=pdf_name,
                peer_id=peer_id
            )
            await send_or_edit(
                peer_id,
                "Твой PDF-файл готов:",
                attachment=doc,
                conv_msg_id=conv_msg_id,
                message_id=msg_id
            )
            os.remove(pdf_name)
        else:
            await send_or_edit(
                peer_id,
                "Не удалось создать PDF. Попробуй позже.",
                conv_msg_id=conv_msg_id,
                message_id=msg_id
            )
    finally:
        stop_dynamic_typing(peer_id)
        await release_lock(f"pdf_gen:{vk_id}")


# ====================== ОРАКУЛ ======================
@labeler.message(func=lambda m: m.payload and m.payload.get("cmd") == "oracle_card")
async def handle_oracle_card(event):
    """Обработка выбора карты в Оракуле"""
    vk_id = event.user_id
    peer_id = event.peer_id
    card_id = event.payload.get("oracle_card")

    if not await acquire_lock(vk_id):
        return

    try:
        await start_dynamic_typing(bot.api, peer_id)

        state = await get_fsm_step(vk_id)
        if not state or state.get("step") != "oracle_draw":
            return

        drawn = state.get("drawn_cards", [])
        if card_id not in drawn:
            drawn.append(card_id)

        if len(drawn) < 3:
            # Обновляем состояние
            state["drawn_cards"] = drawn
            await set_user_state(vk_id, json.dumps(state))

            # Красивое обновление сообщения
            await send_or_edit(
                peer_id=peer_id,
                text=f"Выбрано: {len(drawn)}/3 карт. Продолжай выбирать...",
                conv_msg_id=event.get("conversation_message_id")
            )
        else:
            # Все 3 карты выбраны
            await set_user_state(vk_id, "")
            await send_or_edit(
                peer_id=peer_id,
                text="Отлично! Все карты выбраны. Раскладываю...",
                conv_msg_id=event.get("conversation_message_id")
            )
            # Запускаем финальную обработку
            await process_oracle_final(
                vk_id=vk_id,
                text=state.get("question", ""),
                card_ids=drawn,
                conversation_message_id=event.get("conversation_message_id")
            )
    finally:
        await release_lock(vk_id)


# ====================== ЗАВЕРШЕНИЕ МОДУЛЯ ======================
logger.info("Модуль payments.py загружен успешно")
