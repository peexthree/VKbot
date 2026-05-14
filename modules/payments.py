import asyncio
import datetime
import json
import math
import os
import random
import re
from typing import Any

from loguru import logger
from vkbottle import (
    Callback,
    DocMessagesUploader,
    GroupEventType,
    Keyboard,
    KeyboardButtonColor,
)
from vkbottle.bot import BotLabeler
from vkbottle.tools.dev.keyboard.action import VKPay

from ai_service import extract_tags, generate_section
from cache import acquire_lock, check_throttle, release_lock, set_fsm_state
from cards_data import get_card_data

# Все импорты базы и сервисов — строго здесь
from database import (
    check_and_save_transaction,
    delete_user,
    get_user,
    set_user_state,
    update_user,
)
from modules.admin import process_admin_cmd, show_admin_console
from modules.bot_init import bot
from modules.profile import (
    settings_handler,
    settings_choose_character,
    show_grimoire_page,
    view_card_direct,
)
from modules.profile.settings import process_skin_action_logic
from modules.profile.views import (
    show_guide_logic,
    syndicate_dashboard_logic,
)

# Локальные импорты, перенесенные наверх
from modules.services import show_services, show_tariffs
from modules.tarot import card_of_day_logic, process_oracle_final
from modules.utils import (
    SKIN_ASSETS,
    generate_premium_pdf,
    get_fsm_step,
    get_main_keyboard,
    get_sections_keyboard,
    pdf_semaphore,
    start_dynamic_typing,
    stop_dynamic_typing,
    upload_local_photo,
)

labeler = BotLabeler()

@labeler.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=dict)
async def message_event_handler(event: dict):
    obj = event.get("object", {})
    vk_id = obj.get("user_id")
    peer_id = obj.get("peer_id")
    event_id = obj.get("event_id")
    payload = obj.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            pass

    # Throttling is very important for inline callbacks (MESSAGE_EVENT) as well.
    if vk_id and payload.get("cmd") != "profile_action":
        if await check_throttle(vk_id):
            return

    if not await acquire_lock(vk_id, ttl=2): return
    try:
        if not vk_id or not payload:
            return

        cmd = payload.get("cmd")

        if cmd == "admin_cmd":
            await process_admin_cmd(vk_id, peer_id, payload)
            # Acknowledge the event
            await bot.api.messages.send_message_event_answer(
                event_id=event_id,
                user_id=vk_id,
                peer_id=peer_id
            )
            return
        elif cmd == "admin_cmd_cancel":
            await set_fsm_state(vk_id, "")
            await show_admin_console(peer_id)
            await bot.api.messages.send_message_event_answer(
                event_id=event_id,
                user_id=vk_id,
                peer_id=peer_id
            )
            return
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


            first_name = user.get("purchased_sections", {}).get("first_name", "")
            intro = f"Привет, {first_name}! Твоя натальная карта — это не просто звезды, это код твоего потенциала." if first_name else "Твоя натальная карта — это не просто звезды, это код твоего потенциала."

            kb = Keyboard(inline=True)
            kb.add(Callback("🃏 ПРИНЯТЬ ПЕРВУЮ КАРТУ ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)

            await bot.api.messages.send(
                peer_id=peer_id,
                message=f"Твоя матрица готова...\n\n{intro}\n\n{insight}\n\nПервый шаг: открой Карту Дня.",
                keyboard=kb.get_json(),
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
                    await bot.api.messages.edit(
                        peer_id=peer_id,
                        conversation_message_id=obj.get("conversation_message_id"),
                        message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.",
                        keyboard=kb.get_json()
                    )
                else:
                    await show_services(vk_id, peer_id, 0) # Fallback if they don't own it

        elif cmd == "main_menu":
            user = await get_user(vk_id)
            if not user: return
            kb_json = await get_sections_keyboard(vk_id, user)
            await bot.api.messages.send(peer_id=peer_id, message="ТВОИ ДАННЫЕ В СИСТЕМЕ. КУДА ДВИНЕМСЯ ДАЛЬШЕ?", keyboard=kb_json, random_id=0)

        elif cmd == "card_of_day_menu":
            await card_of_day_logic(
                vk_id, peer_id,
                skip_lock=True,
                event_id=event_id,
                conversation_message_id=obj.get("conversation_message_id")
            )
            return

        elif cmd == "services_menu":
            await show_services(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"))

        elif cmd == "profile_menu":
            from modules.profile.views import show_profile_logic
            await show_profile_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True)

        elif cmd == "guide_menu" or cmd == "guide":
            await show_guide_logic(vk_id, peer_id, skip_lock=True)

        elif cmd == "service_page":
            idx = payload.get("idx", 0)
            await show_services(vk_id, peer_id, idx, edit_msg_id=obj.get("conversation_message_id"))

        elif cmd == "tariff_page":
            idx = payload.get("idx", 0)
            await show_tariffs(vk_id, peer_id, idx, edit_msg_id=obj.get("conversation_message_id"))

        elif cmd == "skin_page":
            idx = payload.get("idx", 0)
            await settings_choose_character(vk_id=vk_id, peer_id=peer_id, skip_lock=True, idx=idx, edit_msg_id=obj.get("conversation_message_id"))

        elif cmd in ["set_skin", "buy_skin"]:
            await process_skin_action_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, payload=payload)

        elif cmd == "card_of_day":
            await card_of_day_logic(
                vk_id, peer_id,
                skip_lock=True,
                event_id=event_id,
                conversation_message_id=obj.get("conversation_message_id")
            )
            return

        elif cmd == "gen_pdf":
            section = payload.get("section", "report")
            card_id = payload.get("card", "")
            user = await get_user(vk_id)
            if not user: return

            latest_data = user.get("latest_reading_data", {})
            if not latest_data and user.get("latest_reading_text"):
                # fallback for old users
                latest_data = {"text": user.get("latest_reading_text")}

            if not latest_data or "text" not in latest_data:
                await bot.api.messages.send(peer_id=peer_id, message="Текст разбора не найден. Сгенерируйте разбор заново.", random_id=0)
                return

            await bot.api.messages.send(peer_id=peer_id, message="Создаю PDF-файл, подожди секунду...", random_id=0)

            pdf_name = f"report_{vk_id}_{section}.pdf"
            b_info = f"{user.get('birth_date')} {user.get('birth_time')} {user.get('birth_city')}"
            first_name = user.get("purchased_sections", {}).get("first_name", "Странник")

            card_data = get_card_data(card_id) if card_id else {}
            card_name = card_data.get("name")
            card_description = card_data.get("description")

            current_date_str = datetime.datetime.now().strftime("%d.%m.%Y")

            async with pdf_semaphore:
                await asyncio.to_thread(
                    generate_premium_pdf,
                    user_name=first_name,
                    birth_info=b_info,
                    section_name=section.upper(),
                    text_content=latest_data.get("text", ""),
                    output_filename=pdf_name,
                    card_id=card_id,
                    advice_content="",
                    card_name=card_name,
                    card_description=card_description,
                    shadow_side=latest_data.get("shadow_side", ""),
                    activation_level=latest_data.get("activation_level", 100),
                    activation_comment=latest_data.get("activation_comment", ""),
                    affirmations=latest_data.get("affirmations", ""),
                    next_activation_date=latest_data.get("next_activation_date", ""),
                    thirty_day_forecast=latest_data.get("thirty_day_forecast", ""),
                    activation_recommendations=latest_data.get("activation_recommendations", ""),
                    star_code=latest_data.get("star_code", ""),
                    energy_map=latest_data.get("energy_map", ""),
                    current_date=current_date_str
                )

            # Отправка
            doc = await DocMessagesUploader(bot.api).upload(title=f"{section}.pdf", file_source=pdf_name, peer_id=peer_id)
            await bot.api.messages.send(peer_id=peer_id, message="Твой PDF-файл готов:", attachment=doc, random_id=0, keyboard=get_main_keyboard())

            if os.path.exists(pdf_name):
                await asyncio.to_thread(os.remove, pdf_name)

        elif cmd == "profile_action":
            action = payload.get("action")
            
          
                
            if action == "settings":
                # Mock a message object
                await settings_handler(vk_id=vk_id, peer_id=peer_id, skip_lock=True)
            elif action == "change_data":
                await set_user_state(vk_id, "waiting_for_onboarding_data")
                kb = Keyboard(inline=True)
                kb.add(Callback("ОТМЕНА", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.NEGATIVE)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Введите новые данные в формате: ДД.ММ.ГГГГ, Время, Город.", keyboard=kb.get_json())
            elif action == "change_skin":
                await settings_choose_character(vk_id=vk_id, peer_id=peer_id, skip_lock=True, edit_msg_id=obj.get("conversation_message_id"))
            elif action == "cancel_sub":
                await update_user(vk_id, {"transit_sub_expires_at": None})
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Транзит (Подписка) успешно отменен.")
            elif action == "reset_account":
                await set_user_state(vk_id, json.dumps({"step": "waiting_reset_confirm"}))
                kb = Keyboard(inline=True)
                kb.add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE)
                kb.row()
                kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс в системе. Вы уверены?", keyboard=kb.get_json())
            elif action == "confirm_reset":
                await delete_user(vk_id)
                await set_user_state(vk_id, "")
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="СИСТЕМА ОБНУЛЕНА. ТЫ ДЛЯ МЕНЯ ТЕПЕРЬ НИКТО. Напиши 'Начать' для старта с нуля.")
            elif action == "back_to_profile":
                from modules.profile.views import show_profile_logic
                await show_profile_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True)
            elif action == "guide":
                await show_guide_logic(vk_id, peer_id, skip_lock=True)
            elif action == "admin_console":
                await show_admin_console(peer_id)
            elif action == "syndicate":
                await syndicate_dashboard_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True)
            elif action == "grimoire":
                await show_grimoire_page(vk_id, peer_id, 0, skip_lock=True)
            elif action == "tariffs":
                await show_tariffs(vk_id, peer_id, 0)
            elif action == "get_seal":
                await set_user_state(vk_id, "")
                text = (
                    "📜 ТВОЯ ПЕЧАТЬ ПРИЗЫВА\n\n"
                    f"Код твоей Печати: ПЕЧАТЬ-{vk_id}\n\n"
                    "Отправь этот код новому адепту, или скинь ему прямую ссылку: "
                    f"https://vk.com/im?sel=-219181948&text=ПЕЧАТЬ-{vk_id}\n\n"
                    "Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд."
                )
                await bot.api.messages.send(peer_id=peer_id, message=text, random_id=0)
            elif action == "enter_seal":
                await set_user_state(vk_id, "waiting_for_seal")
                kb = Keyboard(inline=True)
                kb.add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Введи Печать (код), которую тебе передал Ведущий:", keyboard=kb.get_json())
            elif action == "cancel_seal":
                await set_user_state(vk_id, "")
                await syndicate_dashboard_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True)
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
                    updates: dict[str, str | bool | dict[str, Any]] = {"transit_sub_expires_at": new_expires.isoformat()}
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
                kb.add(Callback("🎁 ПОЗВАТЬ ДРУГА (+500 ✨)", payload={"cmd": "get_referral"}), color=KeyboardButtonColor.POSITIVE)

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
            # Direct link to group 219181948 sending text ПЕЧАТЬ-{vk_id}
            ref_link = f"https://vk.com/im?sel=-219181948&text=ПЕЧАТЬ-{vk_id}"
            await bot.api.messages.send(
                peer_id=peer_id,
                message=f"Твоя персональная ссылка для друзей:\n{ref_link}\n\nОтправь этот код/ссылку новому адепту. Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд.",
                random_id=0
            )

        elif cmd == "grimoire_page":
            page = payload.get("page", 0)
            await show_grimoire_page(vk_id, peer_id, page, skip_lock=True)

        elif cmd == "view_card":
            card_id = str(payload.get("id"))
            await view_card_direct(vk_id, peer_id, card_id, skip_lock=True)

        elif cmd == "global_cut":
            # Если в payload передан target (например, "welcome" для первого разбора), сохраняем его в стейт
            target = payload.get("target")
            if target:
                 await set_user_state(vk_id, json.dumps({
                    "step": "global_cut",
                    "target_section": target
                 }))

            kb = Keyboard(inline=True)
            for i in range(10):
                if i > 0 and i % 5 == 0: kb.row()
                kb.add(Callback("🎴", payload={"cmd": "global_draw"}), color=KeyboardButtonColor.SECONDARY)

            await bot.api.messages.edit(
                peer_id=peer_id,
                message="Выбери карту из разложенных:",
                conversation_message_id=obj.get("conversation_message_id"),
                keyboard=kb.get_json()
            )

        elif cmd == "global_draw":
            await bot.api.messages.edit(
                peer_id=peer_id,
                conversation_message_id=obj.get("conversation_message_id"),
                message="Карта выбрана. Читаю линии вероятности...",
                keyboard=Keyboard(inline=True).get_json()
            )

            state_dict = await get_fsm_step(vk_id)
            if not state_dict: return
            target_section = state_dict.get("target_section", "")
            partner_name = state_dict.get("partner_name", "")
            partner_date = state_dict.get("partner_date", "")
            await set_user_state(vk_id, "")

            # 1. Pick a random card
            card_id = str(random.randint(0, 77))

            # 2. Get Card Data
            card_data = get_card_data(card_id)

            # 3. Add to user DB synchronously
            user = await get_user(vk_id)
            if user:
                unlocked_cards = user.get("unlocked_cards", {})
                if isinstance(unlocked_cards, list):
                    unlocked_cards = dict.fromkeys(unlocked_cards, "Первое касание")
                if card_id not in unlocked_cards:
                    unlocked_cards[card_id] = f"{card_data.get('name', 'Карта')} - {card_data.get('subtitle', 'Новое знание')}"

                current_total = user.get("total_cards_received", 0)
                await update_user(vk_id, {"total_cards_received": current_total + 1, "unlocked_cards": unlocked_cards})

            # Remove previous inline keyboard msg immediately to prevent double-clicks
                from modules.utils import THEATRICAL_PHRASES
            loading_text = random.choice(THEATRICAL_PHRASES)

            await bot.api.messages.edit(
                peer_id=peer_id, message=loading_text,
                conversation_message_id=obj.get("conversation_message_id"), keyboard=Keyboard(inline=True).get_json()
            )
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")

            # 4. Instant Output for the user (Persona + Card Image + Details)
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
    lock_key = f"process_payment_and_generate:{vk_id}"
    if not await acquire_lock(lock_key, ttl=300): return
    try:
        user = await get_user(vk_id)
        if not user: return

        purchased = user.get("purchased_sections", {})
        if section == "all":
            purchased.update({"sex": True, "money": True, "shadow": True, "final": True})
            await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. Все Врата открыты.", random_id=0, keyboard=get_main_keyboard())
            # Тут вызываем логику формирования бандла...
        elif section == "oracle":
            purchased["oracle_access"] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, json.dumps({"step": "waiting_oracle_question"}))
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. НАПИШИ СВОЙ ВОПРОС СУДЬБЕ.", random_id=0, keyboard=get_main_keyboard())
            return
        elif section == "synastry":
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, json.dumps({"step": "waiting_synastry_name"}))
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. НАПИШИ ИМЯ ПАРТНЕРА.", random_id=0, keyboard=get_main_keyboard())
            return
        else:
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.", random_id=0, keyboard=get_main_keyboard())

        # Стартуем FSM для обрезания колоды
        await set_user_state(vk_id, json.dumps({
            "step": "global_cut", "target_section": section
        }))
        kb = Keyboard(inline=True)
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
        await bot.api.messages.send(peer_id=vk_id, message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json(), random_id=0)
    finally:
        await release_lock(lock_key)


async def execute_generation(vk_id: int, peer_id: int, target_section: str, partner_name: str, partner_date: str, card_id: str = None, card_data: dict = None):
    """ПОЛНАЯ ЛОГИКА ГЕНЕРАЦИИ"""
    lock_key = f"execute_generation:{vk_id}"
    if not await acquire_lock(lock_key, ttl=300): return
    try:
        user = await get_user(vk_id)
        if not user: return

        # 1. Показываем прогресс
        typing_task = await start_dynamic_typing(peer_id, bot.api)

        try:
            # 2. Формируем данные
            p = user.get("purchased_sections", {})
            active_skin = user.get("active_skin", "olesya")
            tags = user.get("tags", [])

            # 3. Генерация текста
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")

            res_data = await generate_section(
                target_section, user.get("birth_date"), user.get("birth_time"),
                user.get("birth_city"), user.get("core_profile", ""),
                p.get("first_name", ""), p.get("sex_val", 0),
                partner_name=partner_name, partner_date=partner_date, skin=active_skin,
                card_id=card_id, card_data=card_data, tags=tags, return_json=True
            )

            res_text = res_data.get("text", "") if isinstance(res_data, dict) else res_data

            if res_text:
                # Очищаем текст от тех. тегов ID_ТАРО
                display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", res_text).strip()

                # Save the latest reading data to user's db to use later for PDF generation
                # We also save the text specifically so the fallback works
                save_data = {"latest_reading_text": display_text}
                if isinstance(res_data, dict):
                    # Сохраняем чистую версию текста в объекте данных
                    res_data["text"] = display_text
                    save_data["latest_reading_data"] = res_data
                else:
                    # Если вдруг вернулась строка, создаем минимальный объект
                    save_data["latest_reading_data"] = {"text": display_text}

                await update_user(vk_id, save_data)

                async def extract_and_save_tags(v_id: int, text: str):
                    new_tags = await extract_tags(text)
                    if new_tags:
                        await update_user(v_id, {"tags": new_tags})

                asyncio.create_task(extract_and_save_tags(vk_id, res_text))

                # Build a lightweight keyboard just for PDF generation to avoid VK limits
                light_kb = Keyboard(inline=True)
                light_kb.add(Callback("СГЕНЕРИРОВАТЬ PDF", payload={"cmd": "gen_pdf", "section": target_section, "card": card_id}), color=KeyboardButtonColor.SECONDARY)
                kb_str = light_kb.get_json()

                # Append some premium blocks to the text to preview it in VK
                if isinstance(res_data, dict):
                    act_lvl = res_data.get('activation_level')
                    if act_lvl:
                        display_text += f"\n\n⚡ УРОВЕНЬ АКТИВАЦИИ: {act_lvl}%"
                        if res_data.get('activation_comment'):
                            display_text += f"\n{res_data.get('activation_comment')}"

                    affirmations = res_data.get('affirmations')
                    if affirmations:
                        if isinstance(affirmations, list):
                            affirmations = "\n".join([f"- {a}" for a in affirmations])
                        display_text += f"\n\nТвои аффирмации:\n{affirmations}"

                    display_text += "\n\nПолный разбор со всеми 10 блоками доступен в PDF ниже."

                try:
                    await bot.api.messages.send(
                        peer_id=peer_id,
                        message=display_text,
                        keyboard=kb_str,
                        random_id=0
                    )
                except Exception:
                    await bot.api.messages.send(
                        peer_id=peer_id,
                        message=display_text,
                        random_id=0
                    )
            else:
                await handle_generation_failure(vk_id, peer_id, target_section)
        finally:
            await stop_dynamic_typing(peer_id)
    except Exception as e:
        from modules.utils import stop_dynamic_typing
        await stop_dynamic_typing(peer_id)
        logger.error(f"Ошибка: {str(e)}")
        await handle_generation_failure(vk_id, peer_id, target_section)
    finally:
        await release_lock(lock_key)

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
        message="Кажется, сегодня звёзды немного запутались. Связь прервалась, но твоя Энергия звезд возвращена на баланс. Попробуй ещё раз?",
        random_id=0
    )

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
                message=f"🌟 VK Donut подписка успешно {action}!\nТебе начислено {energy_added} Энергии звезд.\nТвой баланс: {new_balance} ✨.",
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
