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

from ai_service import generate_section
from cache import acquire_lock, check_throttle, release_lock, set_fsm_state
from cards_data import get_card_data
from database import (
    delete_user, get_user, set_user_state, update_user
)
from modules.bot_init import bot
from modules.utils import (
    SKIN_ASSETS, generate_premium_pdf, get_fsm_step, get_main_keyboard,
    get_sections_keyboard, ghost_edit, pdf_semaphore, THEATRICAL_PHRASES, upload_local_photo
)
from modules.admin import process_admin_cmd, show_admin_console
from modules.profile import (
    settings_handler, settings_choose_character, show_grimoire_page, view_card_direct
)
from modules.profile.settings import process_skin_action_logic
from modules.profile.views import show_guide_logic, syndicate_dashboard_logic
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
        except Exception: pass

    if vk_id and payload.get("cmd") != "profile_action":
        if await check_throttle(vk_id): return

    if not await acquire_lock(vk_id, ttl=2): return
    try:
        if not vk_id or not payload: return
        cmd = payload.get("cmd")

        if cmd == "admin_cmd":
            try: await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=vk_id, peer_id=peer_id)
            except Exception: pass
            await process_admin_cmd(vk_id, peer_id, payload)
            return
        elif cmd == "admin_cmd_cancel":
            try: await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=vk_id, peer_id=peer_id)
            except Exception: pass
            await set_fsm_state(vk_id, "")
            await show_admin_console(peer_id)
            return

        logger.info(f"message_event_handler triggered by vk_id={vk_id}, cmd={cmd}")

        try:
            await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=vk_id, peer_id=peer_id)
        except Exception: pass

        if cmd == "retry_registration":
            await set_user_state(vk_id, "waiting_for_onboarding_data")
            await bot.api.messages.edit(peer_id=peer_id, message="Понял. Попробуй еще раз. Напиши дату, время и город рождения максимально четко.", conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "edit_onboarding_data":
            await set_user_state(vk_id, "waiting_for_onboarding_data")
            await bot.api.messages.edit(peer_id=peer_id, message="Для калибровки профиля и начисления 700 Энергии звезд напиши свою дату, время и город рождения одним текстом (например: 15 мая 1990, 14:30, Казань).", conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "confirm_registration":
            state_dict = await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "confirm_data": return
            date, time, city = state_dict.get("date"), state_dict.get("time"), state_dict.get("city")
            await set_user_state(vk_id, "")
            await bot.api.messages.edit(peer_id=peer_id, message="СИНХРОНИЗАЦИЯ ДАННЫХ...", conversation_message_id=obj.get("conversation_message_id"))
            user = await update_user(vk_id, {"birth_date": date, "birth_time": time, "birth_city": city, "balance": 700, "welcome_bonus_received": True})
            await bot.api.messages.send(peer_id=peer_id, message="БАЛАНС УСПЕШНО ПОПОЛНЕН.\nНАЧИСЛЕНО: 700 Энергии звезд.", random_id=0)
            await bot.api.messages.send(peer_id=peer_id, message="Анализирую состояние звезд...", random_id=0)
            insight = await generate_section("base", date, time, city, "", user.get("purchased_sections", {}).get("first_name", ""), user.get("purchased_sections", {}).get("sex_val", 0))
            first_name = user.get("purchased_sections", {}).get("first_name", "")
            intro = f"Привет, {first_name}! Твоя натальная карта — это не просто звезды, это код твоего потенциала." if first_name else "Твоя натальная карта — это не просто звезды, это код твоего потенциала."
            kb = Keyboard(inline=True).add(Callback("🃏 ПРИНЯТЬ ПЕРВУЮ КАРТУ ДНЯ", payload={"cmd": "card_of_day_menu"}), color=KeyboardButtonColor.PRIMARY)
            await bot.api.messages.send(peer_id=peer_id, message=f"Твоя матрица готова...\n\n{intro}\n\n{insight}\n\nПервый шаг: открой Карту Дня.", keyboard=kb.get_json(), random_id=0)
        elif cmd == "use_section":
            target_section = payload.get("key")
            user = await get_user(vk_id)
            if user and target_section:
                purchased = user.get("purchased_sections", {})
                has_access = purchased.get(target_section)
                if target_section in ["sex", "money", "shadow", "final"]:
                    if purchased.get("all") or user.get("has_full_chart"): has_access = True
                if has_access:
                    await set_user_state(vk_id, json.dumps({"step": "global_cut", "target_section": target_section}))
                    kb = Keyboard(inline=True).add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
                    await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json())
                else: await show_services(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "main_menu":
            user = await get_user(vk_id)
            if not user: return
            kb_json = await get_sections_keyboard(vk_id, user)
            await ghost_edit(bot.api, peer_id, message="ТВОИ ДАННЫЕ В СИСТЕМЕ. КУДА ДВИНЕМСЯ ДАЛЬШЕ?", keyboard=kb_json, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "card_of_day_menu":
            await card_of_day_logic(vk_id, peer_id, skip_lock=True, event_id=event_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "services_menu": await show_services(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "profile_menu":
            from modules.profile.views import show_profile_logic
            await show_profile_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "guide_menu" or cmd == "guide": await show_guide_logic(vk_id, peer_id, skip_lock=True, conversation_message_id=conv_id if (conv_id := obj.get("conversation_message_id")) else None)
        elif cmd == "service_page": await show_services(vk_id, peer_id, payload.get("idx", 0), edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "tariff_page": await show_tariffs(vk_id, peer_id, payload.get("idx", 0), edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "skin_page": await settings_choose_character(vk_id=vk_id, peer_id=peer_id, skip_lock=True, idx=payload.get("idx", 0), edit_msg_id=obj.get("conversation_message_id"))
        elif cmd in ["set_skin", "buy_skin"]: await process_skin_action_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, payload=payload, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "card_of_day": await card_of_day_logic(vk_id, peer_id, skip_lock=True, event_id=event_id, conversation_message_id=obj.get("conversation_message_id"))
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
                    await bot.api.messages.send(peer_id=peer_id, message="Твой PDF-файл готов:", attachment=doc, random_id=0, keyboard=get_main_keyboard())
                finally:
                    if os.path.exists(pdf_name): await asyncio.to_thread(os.remove, pdf_name)
            else: await bot.api.messages.send(peer_id=peer_id, message="Ошибка при создании PDF. Пожалуйста, попробуйте позже.", random_id=0)
        elif cmd == "profile_action":
            action, conv_id = payload.get("action"), obj.get("conversation_message_id")
            if action == "settings": await settings_handler(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "change_data":
                await set_user_state(vk_id, "waiting_for_onboarding_data")
                kb = Keyboard(inline=True).add(Callback("ОТМЕНА", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.NEGATIVE)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_id, message="Введите новые данные в формате: ДД.ММ.ГГГГ, Время, Город.", keyboard=kb.get_json())
            elif action == "change_skin": await settings_choose_character(vk_id=vk_id, peer_id=peer_id, skip_lock=True, edit_msg_id=conv_id)
            elif action == "cancel_sub":
                await update_user(vk_id, {"transit_sub_expires_at": None})
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_id, message="Транзит (Подписка) успешно отменен.")
            elif action == "reset_account":
                await set_user_state(vk_id, json.dumps({"step": "waiting_reset_confirm"}))
                kb = Keyboard(inline=True).add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE).row().add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_id, message="⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс в системе. Вы уверены?", keyboard=kb.get_json())
            elif action == "confirm_reset":
                await delete_user(vk_id)
                await set_user_state(vk_id, "")
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=conv_id, message="СИСТЕМА ОБНУЛЕНА. ТЫ ДЛЯ МЕНЯ ТЕПЕРЬ НИКТО. Напиши 'Начать' для старта с нуля.")
            elif action == "back_to_profile":
                from modules.profile.views import show_profile_logic
                await show_profile_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "guide": await show_guide_logic(vk_id, peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "admin_console": await show_admin_console(peer_id)
            elif action == "syndicate": await syndicate_dashboard_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "grimoire": await show_grimoire_page(vk_id, peer_id, 0, skip_lock=True, conversation_message_id=conv_id)
            elif action == "tariffs": await show_tariffs(vk_id, peer_id, 0)
            elif action == "get_seal":
                await set_user_state(vk_id, "")
                await bot.api.messages.send(peer_id=peer_id, message=f"📜 ТВОЯ ПЕЧАТЬ ПРИЗЫВА\n\nКод твоей Печати: ПЕЧАТЬ-{vk_id}\n\nОтправь этот код новому адепту, или скинь ему прямую ссылку: https://vk.com/im?sel=-219181948&text=ПЕЧАТЬ-{vk_id}\n\nКак только он интегрируется в матрицу, ты получишь 500 Энергии звезд.", random_id=0)
            elif action == "enter_seal":
                await set_user_state(vk_id, "waiting_for_seal")
                kb = Keyboard(inline=True).add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Введи Печать (код), которую тебе передал Ведущий:", keyboard=kb.get_json())
            elif action == "cancel_seal":
                await set_user_state(vk_id, "")
                await syndicate_dashboard_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True)
        elif cmd == "buy":
            buy_type, key = payload.get("type"), payload.get("key")
            prices = {"sex": 1000, "money": 900, "shadow": 700, "final": 1200, "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500, "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900}
            amount_needed = prices.get(key)
            if not amount_needed: return
            user = await get_user(vk_id)
            if not user: return
            balance = int(user.get("balance", 0) or 0)
            if balance >= amount_needed:
                new_balance = balance - amount_needed
                await update_user(vk_id, {"balance": new_balance})
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
                    await bot.api.messages.send(peer_id=peer_id, message=f"ОПЛАТА УСПЕШНА.\n\nТранзит продлен до {new_expires.strftime('%d.%m.%Y %H:%M')}.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {new_balance} Энергии звезд.", random_id=0)
            else:
                diff_rubles = math.ceil((amount_needed - balance) / 10)
                kb = Keyboard(inline=True).add(VKPay(hash=f"action=pay-to-group&group_id=219181948&amount={diff_rubles}")).row().add(Callback("🎁 ПОЗВАТЬ ДРУГА (+500 ✨)", payload={"cmd": "get_referral"}), color=KeyboardButtonColor.POSITIVE)
                await ghost_edit(bot.api, peer_id=peer_id, message=f"🛑 НЕДОСТАТОЧНО ЭНЕРГИИ.\nТвой баланс: {balance} ✨. Требуется: {amount_needed} ✨.\nСистема не может вскрыть этот слой матрицы.\n\nОплати недостающие {amount_needed - balance} энергии за {diff_rubles} RUB или позови друга, чтобы получить 500 ✨ бесплатно.", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
        elif cmd == "get_referral":
            await ghost_edit(bot.api, peer_id=peer_id, message=f"Твоя персональная ссылка для друзей:\nhttps://vk.com/im?sel=-219181948&text=ПЕЧАТЬ-{vk_id}\n\nОтправь этот код/ссылку новому адепту. Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд.", conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "grimoire_page": await show_grimoire_page(vk_id, peer_id, payload.get("page", 0), skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "view_card": await view_card_direct(vk_id, peer_id, str(payload.get("id")), skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "global_cut":
            target = payload.get("target")
            if target: await set_user_state(vk_id, json.dumps({"step": "global_cut", "target_section": target}))
            kb = Keyboard(inline=True)
            for i in range(10):
                if i > 0 and i % 2 == 0: kb.row()
                kb.add(Callback("🎴", payload={"cmd": "global_draw"}), color=KeyboardButtonColor.SECONDARY)
            await bot.api.messages.edit(peer_id=peer_id, message="Выбери карту из разложенных:", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
        elif cmd == "global_draw":
            await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Карта выбрана. Читаю линии вероятности...", keyboard=Keyboard(inline=True).get_json())
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
            await bot.api.messages.edit(peer_id=peer_id, message=random.choice(THEATRICAL_PHRASES), conversation_message_id=obj.get("conversation_message_id"), keyboard=Keyboard(inline=True).get_json())
            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")
            active_skin = user.get("active_skin", "olesya") if user else "olesya"
            skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"), peer_id=vk_id)
            card_att = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)
            if skin_att: await bot.api.messages.send(peer_id=peer_id, message="", attachment=skin_att, random_id=0)
            p_display = "Проводник"
            for k, v in SKIN_ASSETS.items():
                if v == SKIN_ASSETS.get(active_skin, "o.png") and k != active_skin:
                    p_display = k
                    break
            await bot.api.messages.send(peer_id=peer_id, message=f"🔮 Проводник: {p_display}\n🃏 Твоя карта: {card_data.get('name')} — {card_data.get('subtitle')}\n📖 Значение: {card_data.get('description')}", attachment=card_att, random_id=0)
            await bot.api.messages.send(peer_id=peer_id, message="Считываю поток для персонализированного разбора...", random_id=0)
            if target_section: asyncio.create_task(execute_generation(vk_id, peer_id, target_section, p_name, p_date, card_id, card_data, conversation_message_id=obj.get("conversation_message_id")))
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
                        if b_cnt > 0 and b_cnt % 2 == 0: kb.row()
                        kb.add(Callback("🎴", payload={"oracle_card": c_id}))
                        b_cnt += 1
                await bot.api.messages.edit(peer_id=peer_id, message=f"Выбрано: {len(drawn)}/3...", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
            else:
                await set_user_state(vk_id, "")
                await bot.api.messages.edit(peer_id=peer_id, message="Выбрано: 3/3. Карты собраны.", conversation_message_id=obj.get("conversation_message_id"), keyboard=Keyboard(inline=True).get_json())
                asyncio.create_task(process_oracle_final(vk_id, state_dict.get("question", ""), drawn))
    finally: await release_lock(vk_id)
