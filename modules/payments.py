from modules.bot_init import bot
import math
import asyncio
import json
from loguru import logger
import random
import re
import datetime
import os
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader, Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from vkbottle.tools.dev.keyboard.action import VKPay

# Все импорты базы и сервисов — строго здесь
from database import get_user, update_user, set_user_state, get_user_state, create_user, check_and_save_transaction
from ai_service import generate_text, generate_section
from modules.utils import (
    generate_premium_pdf, get_fsm_step, upload_local_photo,
    get_dynamic_keyboard, get_sections_keyboard, get_storefront_keyboard, cover_cache, pdf_semaphore
)
from cache import acquire_lock, release_lock, check_throttle

# Локальные импорты, перенесенные наверх
from modules.services import show_services
from modules.services import show_tariffs
from modules.profile import show_grimoire_page
from modules.profile import view_card_direct
from modules.tarot import process_oracle_final, card_of_day_logic
from loguru import logger

labeler = BotLabeler()

@labeler.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=dict)
async def message_event_handler(event: dict):
    obj = event.get("object", {})
    vk_id = obj.get("user_id")
    peer_id = obj.get("peer_id")
    event_id = obj.get("event_id")
    payload = obj.get("payload", {})

    # Throttling is very important for inline callbacks (MESSAGE_EVENT) as well.

    if vk_id and await check_throttle(vk_id): return

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
            logger.error(f"Ошибка: {str(e)}")
            
        # 2. Обработка команд (CALLBACK)
        if cmd == "retry_registration":
            await set_user_state(vk_id, "waiting_for_onboarding_data")
            await bot.api.messages.edit(
                peer_id=peer_id,
                message="Понял. Попробуй еще раз. Напиши дату, время и город рождения максимально четко.",
                conversation_message_id=obj.get("conversation_message_id")
            )
            return

        elif cmd == "edit_onboarding_data":
            await set_user_state(vk_id, "waiting_for_onboarding_data")
            await bot.api.messages.edit(
                peer_id=peer_id,
                message=(
                    "Для калибровки профиля и начисления 700 Энергии звезд напиши свою дату, "
                    "время и город рождения одним текстом (например: 15 мая 1990, 14:30, Казань)."
                ),
                conversation_message_id=obj.get("conversation_message_id")
            )
            return

        elif cmd == "confirm_registration":
            state_dict = await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "confirm_data":
                return

            date = state_dict.get("date")
            time = state_dict.get("time")
            city = state_dict.get("city")

            await set_user_state(vk_id, "")

            # Provide immediate feedback while processing
            await bot.api.messages.edit(
                peer_id=peer_id,
                message="СИНХРОНИЗАЦИЯ ДАННЫХ...",
                conversation_message_id=obj.get("conversation_message_id")
            )
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")


            user = await update_user(vk_id, {
                "birth_date": date,
                "birth_time": time,
                "birth_city": city,
                "balance": 700,
                "welcome_bonus_received": True
            })

            # Notify user of balance top-up immediately
            await bot.api.messages.send(
                peer_id=peer_id,
                message="БАЛАНС УСПЕШНО ПОПОЛНЕН.\nНАЧИСЛЕНО: 700 Энергии звезд.",
                random_id=0
            )

            await bot.api.messages.send(peer_id=peer_id, message="Анализирую состояние звезд...", random_id=0)
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")

            insight = await generate_section(
                "base",
                date,
                time,
                city,
                "",
                user.get("purchased_sections", {}).get("first_name", ""),
                user.get("purchased_sections", {}).get("sex_val", 0)
            )


            await bot.api.messages.send(
                peer_id=peer_id,
                message=f"Твоя матрица готова...\n\n{insight}",
                keyboard=get_dynamic_keyboard(user),
                random_id=0
            )
            return

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

        elif cmd == "card_of_day":

            await card_of_day_logic(vk_id, peer_id)
            return

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

                # VK Pay strictly adheres to API (type: vkpay, hash)
                # referral button payload calls referral logic (assumed "profile_ref" or similar, we'll use a direct link logic or just command)
                kb = Keyboard(inline=True)
                kb.add(VKPay(hash=f"action=pay-to-group&group_id=219181948&amount={diff_rubles}"))
                kb.row()
                kb.add(Text("🎁 ПОЗВАТЬ ДРУГА (+500 ✨)", payload={"cmd": "get_referral"}), color=KeyboardButtonColor.POSITIVE)

                msg_text = (
                    f"🛑 НЕДОСТАТОЧНО ЭНЕРГИИ.\n"
                    f"Твой баланс: {balance} ✨. Требуется: {amount_needed} ✨.\n"
                    f"Система не может вскрыть этот слой матрицы.\n\n"
                    f"Оплати недостающие {diff_energy} энергии за {diff_rubles} RUB или позови друга, чтобы получить 500 ✨ бесплатно."
                )

                await bot.api.messages.send(
                    peer_id=peer_id, 
                    message=msg_text,
                    keyboard=kb.get_json(), random_id=0
                )

        elif cmd == "get_referral":
            bot_domain = "anti_taro_bot" # Fallback if you don't query it dynamically
            try:
                groups_info = await bot.api.groups.get_by_id()
                if groups_info:
                    bot_domain = groups_info[0].screen_name
            except Exception:
                pass

            ref_link = f"https://vk.com/write-{groups_info[0].id}?ref={vk_id}" if 'groups_info' in locals() and groups_info else f"https://vk.com/im?sel=-219181948&ref={vk_id}"
            await bot.api.messages.send(
                peer_id=peer_id,
                message=f"🎁 Твоя реферальная ссылка:\n{ref_link}\n\nОтправь её друзьям. Когда друг перейдет по ссылке и начнет работу с ботом, вы оба получите +500 Энергии звезд.",
                random_id=0
            )

        elif cmd == "grimoire_page":
            page = payload.get("page", 0)
            await show_grimoire_page(vk_id, peer_id, page)

        elif cmd == "view_card":
            card_id = str(payload.get("id"))
            await view_card_direct(vk_id, peer_id, card_id)

        elif cmd == "global_cut":
            # Если в payload передан target (например, "welcome" для первого разбора), сохраняем его в стейт
            target = payload.get("target")
            if target:
                 await set_user_state(vk_id, json.dumps({
                    "step": "global_cut",
                    "target_section": target
                 }))

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

            # 1. Pick a random card
            import random
            card_id = str(random.randint(0, 77))

            # 2. Get Card Data
            from cards_data import get_card_data
            card_data = get_card_data(card_id)

            # 3. Add to user DB synchronously
            user = await get_user(vk_id)
            if user:
                unlocked_cards = user.get("unlocked_cards", {})
                if isinstance(unlocked_cards, list):
                    unlocked_cards = {k: "Первое касание" for k in unlocked_cards}
                if card_id not in unlocked_cards:
                    unlocked_cards[card_id] = f"{card_data.get('name', 'Карта')} - {card_data.get('subtitle', 'Новое знание')}"

                current_total = user.get("total_cards_received", 0)
                await update_user(vk_id, {"total_cards_received": current_total + 1, "unlocked_cards": unlocked_cards})

            # Remove previous inline keyboard msg immediately to prevent double-clicks
            import random
            from modules.utils import THEATRICAL_PHRASES
            loading_text = random.choice(THEATRICAL_PHRASES)

            await bot.api.messages.edit(
                peer_id=peer_id, message=loading_text,
                conversation_message_id=obj.get("conversation_message_id"), keyboard=Keyboard(inline=True).get_json()
            )
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")

            # 4. Instant Output for the user (Persona + Card Image + Details)
            from modules.utils import SKIN_ASSETS
            active_skin = user.get("active_skin", "olesya") if user else "olesya"

            # Upload Skin Image and Card Image
            skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=vk_id)
            card_att = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)

            # Send Persona first
            if skin_att:
                await bot.api.messages.send(peer_id=peer_id, message="", attachment=skin_att, random_id=0)

            # Define persona display name based on skin
            persona_name_display = "Проводник"
            for k, v in SKIN_ASSETS.items():
                if v == SKIN_ASSETS.get(active_skin, "o.png") and k != active_skin:
                    persona_name_display = k
                    break

            msg_text = (
                f"🔮 Проводник: {persona_name_display}\n"
                f"🃏 Твоя карта: {card_data.get('name')} — {card_data.get('subtitle')}\n"
                f"📖 Значение: {card_data.get('description')}"
            )

            if card_att:
                await bot.api.messages.send(peer_id=peer_id, message=msg_text, attachment=card_att, random_id=0)
            else:
                await bot.api.messages.send(peer_id=peer_id, message=msg_text, random_id=0)

            await bot.api.messages.send(peer_id=peer_id, message="Считываю поток для персонализированного разбора...", random_id=0)

            if target_section:
                asyncio.create_task(execute_generation(vk_id, peer_id, target_section, partner_name, partner_date, card_id, card_data))

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

        # event_id is unreliable or absent sometimes, but VKPay transaction usually has an id or we can use the event id
        event_id = event.get('event_id') or str(obj.get('date', 'none'))
        tx_key = f"tx_vkpay_{vk_id}_{amount}_{event_id}"

        if not await acquire_lock(tx_key, ttl=3600): return

        if not vk_id or not amount: return

        # VK sends amount in 1/1000 of a ruble
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

async def process_payment_and_generate(vk_id: int, section: str):
    user = await get_user(vk_id)
    if not user: return

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
        return
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


async def execute_generation(vk_id: int, peer_id: int, target_section: str, partner_name: str, partner_date: str, card_id: str = None, card_data: dict = None):
    """ПОЛНАЯ ЛОГИКА ГЕНЕРАЦИИ"""
    try:
        user = await get_user(vk_id)
        if not user: return

        # 1. Показываем прогресс
        await bot.api.messages.send(peer_id=peer_id, message="🔮 Начинаю таинство разбора. Это займет около минуты...", random_id=0)

        # 2. Формируем данные
        p = user.get("purchased_sections", {})
        active_skin = user.get("active_skin", "olesya")

        # 3. Генерация текста
        await bot.api.messages.set_activity(peer_id=peer_id, type="typing")

        res_text = await generate_section(
            target_section, user.get("birth_date"), user.get("birth_time"),
            user.get("birth_city"), user.get("core_profile", ""),
            p.get("first_name", ""), p.get("sex_val", 0),
            partner_name=partner_name, partner_date=partner_date, skin=active_skin,
            card_id=card_id, card_data=card_data
        )

        if res_text:
            # Очищаем текст от тех. тегов ID_ТАРО
            display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", res_text).strip()

            # 4. Генерация PDF (через asyncio.to_thread чтобы не блокировать event loop)
            pdf_name = f"report_{vk_id}_{target_section}.pdf"
            b_info = f"{user.get('birth_date')} {user.get('birth_time')} {user.get('birth_city')}"
            async with pdf_semaphore:
                await asyncio.to_thread(generate_premium_pdf, p.get("first_name", "Странник"), b_info, target_section.upper(), display_text, pdf_name, card_id)

            # 5. Отправка
            doc = await DocMessagesUploader(bot.api).upload(title=f"{target_section}.pdf", file_source=pdf_name, peer_id=peer_id)
            kb = await get_sections_keyboard(vk_id, user)
            await bot.api.messages.send(peer_id=peer_id, message=display_text, attachment=doc, keyboard=kb, random_id=0)

            if os.path.exists(pdf_name):
                await asyncio.to_thread(os.remove, pdf_name)
        else:
            await handle_generation_failure(vk_id, peer_id, target_section)
    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        await handle_generation_failure(vk_id, peer_id, target_section)

async def handle_generation_failure(vk_id: int, peer_id: int, target_section: str):
    """Возвращает деньги при сбое генерации"""
    prices = {
        "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
        "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500,
        "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900
    }
    price_of_service = prices.get(target_section, 0)

    user = await get_user(vk_id)
    if user and price_of_service > 0:
        await update_user(vk_id, {"balance": user.get("balance", 0) + price_of_service})

    await bot.api.messages.send(
        peer_id=peer_id,
        message="К сожалению, связь с духами прервалась. Твоя Энергия звезд возвращена на баланс. Попробуй еще раз через минуту.",
        random_id=0
    )
