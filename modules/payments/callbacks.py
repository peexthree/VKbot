import asyncio
import datetime
import json
import math
import os
import random
from loguru import logger
from vkbottle import (
    Callback, DocMessagesUploader, GroupEventType, Keyboard, KeyboardButtonColor
)
from vkbottle.bot import BotLabeler
from vkbottle.tools.dev.keyboard.action import VKPay

from cache import acquire_lock, check_throttle, release_lock, set_fsm_state, redis_client
from cards_data import get_card_data
from database import (
    delete_user, get_user, set_user_state, update_user
)
from modules.bot_init import bot
from modules.utils import (
    SKIN_ASSETS, generate_premium_pdf, get_fsm_step, get_main_keyboard,
    ghost_edit, pdf_semaphore, upload_local_photo
)
from modules.utils.consts import MYSTIC_STATUS_PHRASES
from modules.admin import process_admin_cmd, show_admin_console
from modules.profile import (
    settings_handler, settings_choose_character, show_grimoire_page, view_card_direct
)
from modules.profile.settings import process_skin_action_logic
from modules.profile.views import (
    show_guide_logic,
    show_guide_energy_logic,
    show_guide_services_logic,
    show_guide_syndicate_logic,
    show_guide_grimoire_logic,
    syndicate_dashboard_logic
)
from modules.services import show_services, show_tariffs
from modules.tarot import card_of_day_logic, process_oracle_final

from .logic import process_payment_and_generate, execute_generation

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
            logger.error(f"Failed to parse payload: {payload}")

    if not isinstance(payload, dict):
        payload = {}

    # Пытаемся ответить на событие сразу, чтобы убрать спиннер, но только один раз
    if event_id:
        lock_key = f"event_answered:{event_id}"
        if not await redis_client.set(lock_key, "1", ex=30, nx=True):
            logger.debug(f"Event {event_id} already answered or being processed")
            return
        try:
            await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=vk_id, peer_id=peer_id)
        except Exception as e:
            logger.debug(f"Could not answer event {event_id}: {e}")

    if not vk_id: return

    if payload.get("cmd") not in ["profile_action", "main_menu", "services_menu", "profile_menu"]:
        if await check_throttle(vk_id):
            return

    if not await acquire_lock(vk_id, ttl=5):
        logger.warning(f"Could not acquire lock for vk_id={vk_id} in message_event_handler")
        return
    try:
        if not vk_id or not payload: return
        cmd = payload.get("cmd")

        if cmd in ["admin_cmd", "admin_nav", "admin_user_op"]:
            await process_admin_cmd(vk_id, peer_id, payload, conversation_message_id=obj.get("conversation_message_id"))
            return
        elif cmd == "admin_cmd_cancel":
            await set_fsm_state(vk_id, "")
            await show_admin_console(peer_id)
            return

        logger.info(f"message_event_handler triggered by vk_id={vk_id}, cmd={cmd}")

        if cmd == "retry_registration":
            await set_user_state(vk_id, json.dumps({"step": "waiting_for_onboarding_data", "conv_id": obj.get("conversation_message_id")}))
            await bot.api.messages.edit(peer_id=peer_id, message="Понял. Попробуй еще раз. Напиши дату, время и город рождения максимально четко.", conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "edit_onboarding_data":
            await set_user_state(vk_id, json.dumps({"step": "waiting_for_onboarding_data", "conv_id": obj.get("conversation_message_id")}))
            await bot.api.messages.edit(peer_id=peer_id, message="Для калибровки профиля и начисления 700 Энергии звезд напиши свою дату, время и город рождения одним текстом (например: 15 мая 1990, 14:30, Казань).", conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "confirm_registration":
            state_dict = await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "confirm_data": return
            date, time, city = state_dict.get("date"), state_dict.get("time"), state_dict.get("city")
            await set_user_state(vk_id, "")
            await bot.api.messages.edit(peer_id=peer_id, message="✦ СИНХРОНИЗАЦИЯ С МАТРИЦЕЙ...", conversation_message_id=obj.get("conversation_message_id"))

            # Начисляем бонусы и сохраняем данные
            await update_user(vk_id, {
                "birth_date": date,
                "birth_time": time,
                "birth_city": city,
                "balance": 700,
                "welcome_bonus_received": True
            })

            from modules.registration import send_onboarding_teaser
            user = await get_user(vk_id)
            if user:
                purchased = user.get("purchased_sections", {})
                purchased["conversion_step"] = "onboarded"
                await update_user(vk_id, {"purchased_sections": purchased})
            await send_onboarding_teaser(vk_id, peer_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "use_section":
            target_section = payload.get("key")
            user = await get_user(vk_id)
            if user and target_section:
                purchased = user.get("purchased_sections", {})
                has_access = purchased.get(target_section)
                if target_section in ["sex", "money", "shadow", "final"]:
                    if purchased.get("all") or user.get("has_full_chart"): has_access = True
                if has_access:
                    if target_section == "synastry":
                        await set_user_state(vk_id, json.dumps({"step": "waiting_synastry_name"}))
                        await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="ДЛЯ АНАЛИЗА СОЮЗА НАПИШИ ИМЯ ПАРТНЕРА:")
                        return
                    if target_section == "oracle":
                        # We need to trigger the oracle question handler
                        await set_user_state(vk_id, json.dumps({"step": "waiting_oracle_question"}))
                        await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="НАПИШИ СВОЙ ВОПРОС СУДЬБЕ:")
                        return

                    await set_user_state(vk_id, json.dumps({"step": "global_cut", "target_section": target_section}))
                    kb = Keyboard(inline=True).add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
                    await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json())
                else: await show_services(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "main_menu":
            user = await get_user(vk_id)
            if not user: return

            from modules.keyboards import get_main_inline_keyboard
            kb_json = await get_main_inline_keyboard(vk_id, user)

            first_name = user.get("first_name") or "Адепт"
            balance = int(user.get("balance", 0) or 0)
            active_skin = user.get("active_skin", "olesya")

            from modules.utils.logic import calculate_user_rank
            level, rank = calculate_user_rank(user)

            from modules.utils.consts import SKIN_STATUS_PHRASES
            status_phrase = SKIN_STATUS_PHRASES.get(active_skin, "Система готова.")

            # Кэширование динамического статуса (случайный из базы)
            cache_key = f"dynamic_status:{vk_id}"
            cached_status = await redis_client.get(cache_key)
            if cached_status:
                status_phrase = cached_status
            else:
                try:
                    status_phrase = random.choice(MYSTIC_STATUS_PHRASES)
                    await redis_client.set(cache_key, status_phrase, ex=21600)
                except: pass

            # Визуальный стрик (Лунный цикл)
            visit_streak = user.get("visit_streak", 0)
            moons = ["🌑", "🌘", "🌗", "🌖", "🌕", "✨", "🔥"]
            streak_visual = "".join(moons[i % len(moons)] if i < visit_streak else "○" for i in range(7))

            main_menu_text = (
                "✦ АНТИ-ТАР ✦\n\n"
                f"Привет, {first_name}!\n"
                f"Уровень {level} • {rank} ⭐ {balance} Энергии\n"
                f"Цикл: {streak_visual} ({visit_streak} дн.)\n\n"
                f"🔮 {status_phrase}"
            )

            att = await upload_local_photo(bot.api, "uslugi/main_menu.jpg", peer_id=vk_id)

            await ghost_edit(bot.api, peer_id, message=main_menu_text, keyboard=kb_json, attachment=att, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "card_of_day_menu":
            await card_of_day_logic(vk_id, peer_id, skip_lock=True, event_id=event_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "services_menu": await show_services(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"), filter_val=payload.get("filter"))
        elif cmd == "profile_menu":
            from modules.profile.views import show_profile_logic
            await show_profile_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "natal_chart_menu":
            user = await get_user(vk_id)
            if not user: return
            from modules.keyboards import get_natal_chart_inline_keyboard
            kb_json = get_natal_chart_inline_keyboard(user.get("purchased_sections", {}))
            att = await upload_local_photo(bot.api, "uslugi/services.jpg", peer_id=vk_id)
            await ghost_edit(bot.api, peer_id, "🔮 ТВОЯ НАТАЛЬНАЯ КАРТА\n\nВыбери раздел для глубокого погружения. Каждый разбор можно получить один раз.", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb_json, attachment=att)
        elif cmd == "history_menu":
            from modules.profile.views import show_history_logic
            await show_history_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "view_history":
            from modules.profile.views import show_history_item_logic
            await show_history_item_logic(vk_id=vk_id, peer_id=peer_id, idx=payload.get("idx", 0), skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "admin_console":
            await show_admin_console(peer_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "guide_menu" or cmd == "guide": await show_guide_logic(vk_id, peer_id, skip_lock=True, conversation_message_id=conv_id if (conv_id := obj.get("conversation_message_id")) else None)
        elif cmd == "guide_energy": await show_guide_energy_logic(vk_id, peer_id, conversation_message_id=obj.get("conversation_message_id"), skip_lock=True)
        elif cmd == "guide_services": await show_guide_services_logic(vk_id, peer_id, conversation_message_id=obj.get("conversation_message_id"), skip_lock=True)
        elif cmd == "guide_syndicate": await show_guide_syndicate_logic(vk_id, peer_id, conversation_message_id=obj.get("conversation_message_id"), skip_lock=True)
        elif cmd == "guide_grimoire": await show_guide_grimoire_logic(vk_id, peer_id, conversation_message_id=obj.get("conversation_message_id"), skip_lock=True)
        elif cmd == "service_page": await show_services(vk_id, peer_id, payload.get("idx", 0), edit_msg_id=obj.get("conversation_message_id"), filter_val=payload.get("filter"))
        elif cmd == "tariff_page": await show_tariffs(vk_id, peer_id, payload.get("idx", 0), edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "skin_page": await settings_choose_character(vk_id=vk_id, peer_id=peer_id, skip_lock=True, idx=payload.get("idx", 0), edit_msg_id=obj.get("conversation_message_id"))
        elif cmd in ["set_skin", "buy_skin"]: await process_skin_action_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, payload=payload, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "card_of_day": await card_of_day_logic(vk_id, peer_id, skip_lock=True, event_id=event_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "choose_onboarding_skin":
            from modules import registration as reg_mod
            await reg_mod.process_onboarding_skin_logic(vk_id, peer_id, payload.get("skin"), conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "gen_pdf":
            section, card_id = payload.get("section", "report"), payload.get("card", "")
            user = await get_user(vk_id)
            if not user: return
            latest_data = user.get("latest_reading_data", {})
            if not latest_data and user.get("latest_reading_text"): latest_data = {"text": user.get("latest_reading_text")}
            if not latest_data or "text" not in latest_data:
                await bot.api.messages.send(peer_id=peer_id, message="Текст разбора не найден. Сгенерируйте разбор заново.", random_id=0)
                return
            await bot.api.messages.send(peer_id=peer_id, message="Создаю PDF-файл, подожди секунду...", random_id=0)
            pdf_name = f"report_{vk_id}_{section}.pdf"
            b_info = f"{user.get('birth_date')} {user.get('birth_time')} {user.get('birth_city')}"
            first_name = user.get("purchased_sections", {}).get("first_name", "Странник")
            card_data = get_card_data(card_id) if card_id else {}
            current_date_str = datetime.datetime.now().strftime("%d.%m.%Y")
            async with pdf_semaphore:
                success = await asyncio.to_thread(generate_premium_pdf, user_name=first_name, birth_info=b_info, section_name=section.upper(), text_content=latest_data.get("text", ""), output_filename=pdf_name, card_id=card_id, advice_content="", card_name=card_data.get("name"), card_description=card_data.get("description"), shadow_side=latest_data.get("shadow_side", ""), activation_level=latest_data.get("activation_level", 100), activation_comment=latest_data.get("activation_comment", ""), affirmations=latest_data.get("affirmations", ""), next_activation_date=latest_data.get("next_activation_date", ""), thirty_day_forecast=latest_data.get("thirty_day_forecast", ""), activation_recommendations=latest_data.get("activation_recommendations", ""), star_code=latest_data.get("star_code", ""), energy_map=latest_data.get("energy_map", ""), current_date=current_date_str)
            if success and os.path.exists(pdf_name):
                try:
                    doc = await DocMessagesUploader(bot.api).upload(title=f"{section}.pdf", file_source=pdf_name, peer_id=peer_id)

                    from modules.keyboards import get_main_reply_keyboard
                    await bot.api.messages.send(peer_id=peer_id, message="Твой PDF-файл готов:", attachment=doc, random_id=0, keyboard=get_main_reply_keyboard(vk_id))

                finally:
                    if os.path.exists(pdf_name): await asyncio.to_thread(os.remove, pdf_name)
            else: await bot.api.messages.send(peer_id=peer_id, message="Ошибка при создании PDF. Пожалуйста, попробуйте позже.", random_id=0)
        elif cmd == "profile_action":
            action, conv_id = payload.get("action"), obj.get("conversation_message_id")
            if action == "settings": await settings_handler(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "advanced_settings":
                from modules.profile.handlers import show_advanced_settings
                await show_advanced_settings(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "change_data":
                await set_user_state(vk_id, json.dumps({"step": "waiting_for_onboarding_data", "conv_id": conv_id}))
                kb = Keyboard(inline=True).add(Callback("ОТМЕНА", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.NEGATIVE)
                att = await upload_local_photo(bot.api, "uslugi/settings.jpg", peer_id=vk_id)
                await ghost_edit(bot.api, peer_id, conversation_message_id=conv_id, message="Введите новые данные в формате: ДД.ММ.ГГГГ, Время, Город.", keyboard=kb.get_json(), attachment=att)
            elif action == "change_skin": await settings_choose_character(vk_id=vk_id, peer_id=peer_id, skip_lock=True, edit_msg_id=conv_id)
            elif action == "cancel_sub":
                await update_user(vk_id, {"transit_sub_expires_at": None})
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_id, message="Транзит (Подписка) успешно отменен.")
            elif action == "reset_account":
                await set_user_state(vk_id, json.dumps({"step": "waiting_reset_confirm"}))
                kb = Keyboard(inline=True).add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE).row().add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
                att = await upload_local_photo(bot.api, "uslugi/settings.jpg", peer_id=vk_id)
                await ghost_edit(bot.api, peer_id, conversation_message_id=conv_id, message="⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс в системе. Вы уверены?", keyboard=kb.get_json(), attachment=att)
            elif action == "confirm_reset":
                await delete_user(vk_id)
                await set_user_state(vk_id, "")
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_id, message="СИСТЕМА ОБНУЛЕНА. ТЫ ДЛЯ МЕНЯ ТЕПЕРЬ НИКТО. Напиши 'Начать' для старта с нуля.")
            elif action == "back_to_profile":
                from modules.profile.views import show_profile_logic
                await show_profile_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "guide": await show_guide_logic(vk_id, peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "admin_console": await show_admin_console(peer_id, conversation_message_id=conv_id)
            elif action == "syndicate": await syndicate_dashboard_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "grimoire": await show_grimoire_page(vk_id, peer_id, 0, skip_lock=True, conversation_message_id=conv_id)
            elif action == "tariffs": await show_tariffs(vk_id, peer_id, 0)
            elif action == "get_seal":
                from modules.profile.views import get_seal_logic
                await get_seal_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "enter_seal":
                await set_user_state(vk_id, "waiting_for_seal")
                kb = Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Введи Печать (код), которую тебе передал Ведущий:", keyboard=kb.get_json())
            elif action == "cancel_seal":
                await set_user_state(vk_id, "")
                await syndicate_dashboard_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True)
        elif cmd == "buy":
            buy_type, key = payload.get("type"), payload.get("key")
            prices = {
                "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
                "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500,
                "oracle_upsell": 250,
                "micro_insight": 100,
                "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900,
                "topup_500": 500, "topup_1000": 1000, "topup_5000": 5000
            }
            amount_needed = prices.get(key)
            if not amount_needed: return
            user = await get_user(vk_id)
            if not user: return
            balance = int(user.get("balance", 0) or 0)

            # Process dynamically calculated discounts via abandoned cart payload
            if buy_type in ["abandoned_10", "abandoned_15"]:
                amount_needed = int(amount_needed * (0.90 if buy_type == "abandoned_10" else 0.85))
                buy_type = "service" if key in ["sex", "money", "shadow", "final", "synastry", "all", "oracle", "antitaro", "micro_insight"] else "tariff" if key.startswith("tariff_") else "topup"

            # Для прямых пополнений сразу ведем на оплату
            if buy_type == "topup" or key.startswith("topup_"):
                rubles = amount_needed # Курс 1:1

                # Трекинг брошенной корзины
                p = user.get("purchased_sections", {})
                p["last_cart_item"] = key
                p["last_cart_stage"] = 0
                p["last_cart_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                await update_user(vk_id, {"purchased_sections": p})

                kb = Keyboard(inline=True).add(VKPay(hash=f"action=pay-to-group&group_id=219181948&amount={rubles}"))
                await ghost_edit(bot.api, peer_id, f"💳 ПОПОЛНЕНИЕ БАЛАНСА\n\nВы выбрали пакет: {amount_needed} ✨\nСтоимость: {rubles} RUB\n\nНажмите кнопку ниже для оплаты через VK Pay.", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
                return

            if balance >= amount_needed:
                new_balance = balance - amount_needed
                await update_user(vk_id, {"balance": new_balance})

                if key == "oracle_upsell": key = "oracle" # resolve the upsell back to its base service

                if buy_type == "service": await process_payment_and_generate(vk_id, key)
                elif buy_type == "tariff":
                    days = 7 if key == "tariff_1" else 30
                    new_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
                    updates = {"transit_sub_expires_at": new_expires.isoformat()}
                    if key == "tariff_vip":
                        p = user.get("purchased_sections", {})
                        for s in ["sex", "money", "shadow", "final"]: p[s] = True
                        updates["purchased_sections"], updates["has_full_chart"] = p, True
                    await update_user(vk_id, updates)
                    await bot.api.messages.send(peer_id=peer_id, message=f"ОПЛАТА УСПЕШНА.\n\nТранзит продлен до {new_expires.strftime('%d.%m.%Y %H:%M')}.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {new_balance} Энергии звезд.", random_id=0, keyboard=get_main_keyboard(vk_id))
            else:
                diff_rubles = math.ceil((amount_needed - balance) / 10)
                kb = Keyboard(inline=True).add(VKPay(hash=f"action=pay-to-group&group_id=219181948&amount={diff_rubles}")).row()
                kb.add(Callback("🎁 ПОЗВАТЬ ДРУГА (+500 ✨)", payload={"cmd": "get_referral"}), color=KeyboardButtonColor.POSITIVE).row()
                kb.add(Callback("📜 ПУБЛИЧНАЯ ОФЕРТА", payload={"cmd": "show_offer"}), color=KeyboardButtonColor.SECONDARY)
                await ghost_edit(bot.api, peer_id=peer_id, message=f"🛑 НЕДОСТАТОЧНО ЭНЕРГИИ.\nТвой баланс: {balance} ✨. Требуется: {amount_needed} ✨.\nСистема не может вскрыть этот слой матрицы.\n\nОплати недостающие {amount_needed - balance} энергии за {diff_rubles} RUB или позови друга, чтобы получить 500 ✨ бесплатно.\n\nСовершая оплату, вы принимаете условия публичной оферты.", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
        elif cmd == "get_referral":
            from modules.profile.views import get_seal_logic
            await get_seal_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "grimoire_page": await show_grimoire_page(vk_id, peer_id, payload.get("page", 0), skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "view_card": await view_card_direct(vk_id, peer_id, str(payload.get("id")), skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "show_offer":
            offer_url = "https://telegra.ph/PUBLICHNAYA-OFERTA-NA-OKAZANIE-INFORMACIONNO-RAZVLEKATELNYH-USLUG-05-04"
            await bot.api.messages.send(peer_id=peer_id, message=f"📜 ПУБЛИЧНАЯ ОФЕРТА:\n{offer_url}", random_id=0)
        elif cmd == "global_cut":
            target = payload.get("target")
            if target: await set_user_state(vk_id, json.dumps({"step": "global_cut", "target_section": target}))
            kb = Keyboard(inline=True)
            # 2x5 grid to fit within 6 rows limit
            for _i in range(10):
                kb.add(Callback("🎴", payload={"cmd": "global_draw"}), color=KeyboardButtonColor.SECONDARY)
                if (_i + 1) % 2 == 0 and _i < 9:
                    kb.row()
            await bot.api.messages.edit(peer_id=peer_id, message="Выбери карту из разложенных:", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
        elif cmd == "global_draw":
            # 1. Сразу убираем кнопки и показываем статус
            conv_id = obj.get("conversation_message_id")
            await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_id, message="✦ КАРТА ВЫБРАНА. ИНИЦИАЦИЯ...", keyboard=Keyboard(inline=True).get_json())

            state_dict = await get_fsm_step(vk_id)
            if not state_dict: return
            target_section, p_name, p_date = state_dict.get("target_section", ""), state_dict.get("partner_name", ""), state_dict.get("partner_date", "")
            await set_user_state(vk_id, "")

            card_id = str(random.randint(0, 77))
            card_data = get_card_data(card_id)
            user = await get_user(vk_id)

            if user:
                unlocked = user.get("unlocked_cards")
                if not isinstance(unlocked, dict): unlocked = {str(c): "Первое касание" for c in unlocked} if isinstance(unlocked, list) else {}
                if card_id not in unlocked: unlocked[card_id] = f"{card_data.get('name', 'Карта')} - {card_data.get('subtitle', 'Новое знание')}"
                await update_user(vk_id, {"total_cards_received": user.get("total_cards_received", 0) + 1, "unlocked_cards": unlocked})

            # 2. Подготовка ассетов
            active_skin = user.get("active_skin", "olesya") if user else "olesya"
            skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=vk_id)
            card_att = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)

            atts = []
            if skin_att: atts.append(skin_att)
            if card_att: atts.append(card_att)

            p_display = "Проводник"
            for k, v in SKIN_ASSETS.items():
                if v == SKIN_ASSETS.get(active_skin, "o.png") and k != active_skin:
                    p_display = k
                    break

            # 3. Обновляем ТЕКУЩЕЕ сообщение, добавляя информацию о карте и картинки
            ritual_text = (
                f"🔮 Проводник: {p_display}\n"
                f"🃏 Твоя карта: {card_data.get('name')} — {card_data.get('subtitle')}\n"
                f"📖 Значение: {card_data.get('description')}\n\n"
                "------------------\n"
                "✦ СЧИТЫВАЮ ПОТОК ДЛЯ ПЕРСОНАЛИЗИРОВАННОГО РАЗБОРА..."
            )

            await bot.api.messages.edit(
                peer_id=peer_id,
                conversation_message_id=conv_id,
                message=ritual_text,
                attachment=",".join(atts) if atts else None
            )

            # 4. Запускаем генерацию. ВАЖНО: не передаем conversation_message_id,
            # чтобы результат пришел НОВЫМ сообщением и не стер карту.
            if target_section:
                asyncio.create_task(execute_generation(
                    vk_id, peer_id, target_section, p_name, p_date,
                    card_id, card_data
                ))
        elif "oracle_card" in payload:
            card_id, state_dict = payload["oracle_card"], await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "oracle_draw": return
            drawn, pool = state_dict.get("drawn_cards", []), state_dict.get("pool", [])
            if card_id not in drawn: drawn.append(card_id)
            if len(drawn) < 3:
                state_dict["drawn_cards"] = drawn
                await set_user_state(vk_id, json.dumps(state_dict))
                kb, b_cnt = Keyboard(inline=True), 0
                for c_id in pool:
                    if c_id not in drawn:
                        kb.add(Callback("🎴", payload={"oracle_card": c_id}))
                        b_cnt += 1
                        if b_cnt % 2 == 0:
                            kb.row()
                await bot.api.messages.edit(peer_id=peer_id, message=f"Выбрано: {len(drawn)}/3...", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
            else:
                await set_user_state(vk_id, "")
                await bot.api.messages.edit(peer_id=peer_id, message="Выбрано: 3/3. Карты собраны.", conversation_message_id=obj.get("conversation_message_id"), keyboard=Keyboard(inline=True).get_json())
                asyncio.create_task(process_oracle_final(vk_id, state_dict.get("question", ""), drawn))
    finally: await release_lock(vk_id)
