import random
import asyncio
import datetime
import json
import re
import hashlib
from loguru import logger
from vkbottle import Keyboard, Callback, KeyboardButtonColor
from database import get_user, update_user, set_user_state
from modules.bot_init import bot
from ai_service import generate_section, extract_tags
from modules.utils import (
    get_main_keyboard, ghost_edit,
    start_dynamic_typing, stop_dynamic_typing,
    extract_msg_id
)
from cache import acquire_lock, release_lock

async def process_payment_and_generate(vk_id: int, section: str):
    lock_key = f"process_payment_and_generate:{vk_id}"
    if not await acquire_lock(lock_key, ttl=300): return
    try:
        user = await get_user(vk_id)
        if not user: return

        # Проверка данных в Redis перед генерацией
        from cache import get_temp_birth_data
        birth_data = await get_temp_birth_data(vk_id)

        # Для микро-инсайта, услуг и т.д. нам нужны данные
        if not birth_data and section not in ["oracle", "antitaro"]:
            # Пытаемся спарсить из ВК
            try:
                users_info = await bot.api.users.get(user_ids=[vk_id], fields=["bdate", "city"])
                bdate, city = "", ""
                if users_info:
                    info = users_info[0]
                    bdate = info.bdate or ""
                    if info.city and hasattr(info.city, "title"): city = info.city.title

                original_intent = {"cmd": "process_payment_and_generate", "section": section}

                if bdate and city:
                    # Данные есть в ВК, предлагаем подтвердить
                    state_dict = {
                        "step": "confirm_data",
                        "date": bdate,
                        "time": "12:00",
                        "city": city,
                        "original_intent": original_intent
                    }
                    await set_user_state(vk_id, json.dumps(state_dict))

                    kb = Keyboard(inline=True)
                    kb.add(Callback("✅ ВЕРНО", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
                    kb.row().add(Callback("🔄 ИЗМЕНИТЬ", payload={"cmd": "edit_onboarding_data"}), color=KeyboardButtonColor.NEGATIVE)

                    text = (
                        "🔮 ДАННЫЕ СТЕРТЫ В ЦЕЛЯХ БЕЗОПАСНОСТИ\n\n"
                        "Чтобы я могла провести ритуал, пожалуйста, проверь верны ли твои данные:\n\n"
                        f"☾ Дата: {bdate}\n"
                        f"☾ Город: {city}\n"
                        "☾ Время: 12:00 (по умолчанию)\n\n"
                        "Всё верно?"
                    )
                    await bot.api.messages.send(peer_id=vk_id, message=text, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                    return
            except Exception as e:
                logger.error(f"Error parsing VK data during process_payment: {e}")

            await set_user_state(vk_id, json.dumps({
                "step": "waiting_birth_date",
                "target_section": section,
                "is_upsell": (section == "oracle_upsell"),
                "original_intent": {"cmd": "process_payment_and_generate", "section": section}
            }))
            await bot.api.messages.send(
                peer_id=vk_id,
                message="🔮 ДАННЫЕ СТЕРТЫ В ЦЕЛЯХ БЕЗОПАСНОСТИ\n\nЧтобы я могла продолжить чтение твоей судьбы, мне нужно заново настроиться на твою энергию. Шепни мне свою ДАТУ рождения (например, 15.04.1990):",
                random_id=random.getrandbits(63)
            )
            return

        if section == "micro_insight":
            active_skin = user.get("active_skin", "olesya")
            from modules.utils.consts import SKIN_DISPLAY_NAMES
            character_name = SKIN_DISPLAY_NAMES.get(active_skin, "Проводник")
            from ai_service import generate_text
            from modules.utils.logic import get_safe_tags
            b_info = f"{birth_data.get('date')} {birth_data.get('city')}"
            prompt = (
                f"Пользователь купил микро-инсайт. Его данные: {b_info}. "
                f"Теги: {get_safe_tags(user)}. "
                f"Дай ОДИН короткий, дерзкий и точный совет или предсказание на ближайший час. "
                f"Стиль: {active_skin} (имя: {character_name}). Максимум 2 предложения. Без жирного шрифта."
            )
            insight = await generate_text(prompt, skin=active_skin, is_background=False)
            if not insight or insight == "ERROR_RPM_LIMIT":
                # Универсальный возврат через handle_generation_failure
                await handle_generation_failure(vk_id, vk_id, "micro_insight")
                return

            from modules.keyboards import get_main_reply_keyboard
            await bot.api.messages.send(
                peer_id=vk_id,
                message=f"✦ ШЕПОТ МАТРИЦЫ ✦\n\n{insight}",
                random_id=random.getrandbits(63),
                keyboard=get_main_reply_keyboard(vk_id)
            )
            # Призрачный интерфейс: возвращаем пользователя в меню услуг
            from modules.services import show_services
            await show_services(vk_id, vk_id, 0, is_catalog=True)
            return

        purchased = user.get("purchased_sections", {})
        if section == "all":
            purchased.update({"sex": True, "money": True, "shadow": True, "final": True, "all": True})
            await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. Все Врата открыты.", random_id=random.getrandbits(63), keyboard=get_main_keyboard(vk_id))
        elif section == "oracle":
            purchased["oracle_access"] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, '{"step": "waiting_oracle_question"}')
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. НАПИШИ СВОЙ ВОПРОС СУДЬБЕ.", random_id=random.getrandbits(63), keyboard=get_main_keyboard(vk_id))
            return
        elif section == "synastry":
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, '{"step": "waiting_synastry_name"}')
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. НАПИШИ ИМЯ ПАРТНЕРА.", random_id=random.getrandbits(63), keyboard=get_main_keyboard(vk_id))
            return
        elif section == "palmistry":
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, '{"step": "waiting_palmistry_photos"}')
            msg = (
                "✅ Оплата прошла. Теперь для точного анализа пришлите в одном сообщении две фотографии:\n\n"
                "• Левая ладонь (врожденный потенциал)\n"
                "• Правая ладонь (текущая реализация)\n\n"
                "Требования:\n"
                "- Хорошее освещение\n"
                "- Ладонь полностью в кадре\n"
                "- Пальцы выпрямлены\n"
                "- Крупный план"
            )
            await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=random.getrandbits(63), keyboard=get_main_keyboard(vk_id))
            return
        elif section == "dream":
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, '{"step": "waiting_dream_text"}')
            msg = (
                "✅ Оплата прошла. Расскажи мне свой сон подробным текстом.\n\n"
                "Можно добавить:\n"
                "- Когда приснился (дата/время)\n"
                "- Настроение после пробуждения\n"
                "- Любые важные детали\n\n"
                "Чем подробнее опишешь - тем точнее будет разбор."
            )
            await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=random.getrandbits(63), keyboard=get_main_keyboard(vk_id))
            return
        else:
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            # Призрачный интерфейс: удаляем старое и шлем подтверждение
            from modules.utils import delete_bot_message, get_last_bot_msg, set_last_bot_msg
            last_mid = await get_last_bot_msg(vk_id)
            if last_mid:
                await delete_bot_message(bot.api, vk_id, mid=last_mid)

            msg_id = await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.", random_id=random.getrandbits(63), keyboard=get_main_keyboard(vk_id))
            await set_last_bot_msg(vk_id, msg_id)

        await set_user_state(vk_id, f'{{"step": "global_cut", "target_section": "{section}"}}')
        kb = Keyboard(inline=True)
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
        await bot.api.messages.send(peer_id=vk_id, message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json(), random_id=random.getrandbits(63))
    finally:
        await release_lock(lock_key)

async def execute_generation(
    vk_id: int,
    peer_id: int,
    target_section: str,
    partner_name: str,
    partner_date: str,
    card_id: str = None,
    card_data: dict = None,
    conversation_message_id: int = None
):
    lock_key = f"execute_generation:{vk_id}"
    if not await acquire_lock(lock_key, ttl=300): return
    try:
        user = await get_user(vk_id)
        if not user: return

        # Мгновенная реакция: заглушка перед стартом тяжелых процессов
        wait_msg = "🔮 Оракул настраивает связь с инфополем, подожди немного..."
        if conversation_message_id:
            await ghost_edit(bot.api, peer_id, wait_msg, conversation_message_id=conversation_message_id)
        else:
            resp = await bot.api.messages.send(peer_id=peer_id, message=wait_msg, random_id=random.getrandbits(63))
            conversation_message_id = extract_msg_id(resp)

        # Если мы не редактируем старое сообщение, то dynamic_typing создаст новое
        typing_task = await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)

        try:
            p = user.get("purchased_sections", {})
            active_skin = user.get("active_skin", "olesya")
            from modules.utils.logic import get_safe_tags
            tags = get_safe_tags(user)

            # Улучшенное получение имени и пола
            u_name = user.get("first_name") or p.get("first_name", "Адепт")
            u_sex = user.get("sex_val") if "sex_val" in user else p.get("sex_val", 0)

            current_date_str = datetime.datetime.now().strftime("%d.%m.%Y")

            await bot.api.messages.set_activity(peer_id=peer_id, type="typing")

            image_urls = None
            if target_section == "palmistry":
                from cache import redis_client
                res = await redis_client.get(f"palmistry_photos:{vk_id}")
                if res:
                    image_urls = json.loads(res)

            if target_section == "dream":
                from cache import redis_client
                dream_text = await redis_client.get(f"dream_text:{vk_id}")
                if dream_text:
                    partner_date = dream_text.decode() if isinstance(dream_text, bytes) else dream_text

            from cache import get_temp_birth_data
            birth_data = await get_temp_birth_data(vk_id)
            if not birth_data:
                # В теории мы уже проверили это в process_payment_and_generate, но для надежности
                await stop_dynamic_typing(peer_id)

                original_intent = {
                    "cmd": "execute_generation",
                    "target_section": target_section,
                    "partner_name": partner_name,
                    "partner_date": partner_date,
                    "card_id": card_id,
                    "card_data": card_data
                }

                # Пытаемся спарсить из ВК
                try:
                    users_info = await bot.api.users.get(user_ids=[vk_id], fields=["bdate", "city"])
                    bdate, city = "", ""
                    if users_info:
                        info = users_info[0]
                        bdate = info.bdate or ""
                        if info.city and hasattr(info.city, "title"): city = info.city.title

                    if bdate and city:
                        # Данные есть в ВК, предлагаем подтвердить
                        state_dict = {
                            "step": "confirm_data",
                            "date": bdate,
                            "time": "12:00",
                            "city": city,
                            "conv_id": conversation_message_id,
                            "original_intent": original_intent
                        }
                        await set_user_state(vk_id, json.dumps(state_dict))

                        kb = Keyboard(inline=True)
                        kb.add(Callback("✅ ВЕРНО", payload={"cmd": "confirm_registration"}), color=KeyboardButtonColor.POSITIVE)
                        kb.row().add(Callback("🔄 ИЗМЕНИТЬ", payload={"cmd": "edit_onboarding_data"}), color=KeyboardButtonColor.NEGATIVE)

                        text = (
                            "🔮 ДАННЫЕ СТЕРТЫ В ЦЕЛЯХ БЕЗОПАСНОСТИ\n\n"
                            "Чтобы я могла завершить ритуал, пожалуйста, проверь верны ли твои данные:\n\n"
                            f"☾ Дата: {bdate}\n"
                            f"☾ Город: {city}\n"
                            "☾ Время: 12:00 (по умолчанию)\n\n"
                            "Всё верно?"
                        )
                        if conversation_message_id:
                            await ghost_edit(bot.api, peer_id, text, conversation_message_id=conversation_message_id, keyboard=kb.get_json())
                        else:
                            await bot.api.messages.send(peer_id=peer_id, message=text, keyboard=kb.get_json(), random_id=random.getrandbits(63))
                        return
                except Exception as e:
                    logger.error(f"Error parsing VK data during execute_generation: {e}")

                await set_user_state(vk_id, json.dumps({
                    "step": "waiting_birth_date",
                    "target_section": target_section,
                    "original_intent": original_intent
                }))
                await bot.api.messages.send(peer_id=peer_id, message="🔮 ДАННЫЕ СТЕРТЫ В ЦЕЛЯХ БЕЗОПАСНОСТИ\n\nЧтобы завершить ритуал, шепни мне дату своего рождения (например, 15.04.1990):", random_id=random.getrandbits(63))
                return

            from cache import get_core_profile
            core_profile = await get_core_profile(vk_id)

            res_data = await generate_section(
                target_section, birth_data.get("date"), birth_data.get("time"),
                birth_data.get("city"), core_profile,
                u_name, u_sex,
                partner_name=partner_name, partner_date=partner_date, skin=active_skin,
                card_id=card_id, card_data=card_data, tags=tags, return_json=True,
                current_date=current_date_str,
                image_urls=image_urls,
                purchased_skins=user.get("purchased_skins", [])
            )

            res_text = res_data.get("text", "") if isinstance(res_data, dict) else res_data

            if res_text == "ERROR_RPM_LIMIT":
                msg = "Оракул перегружен космической энергией. Попробуй запустить ритуал через 30 секунд ✨"
                await stop_dynamic_typing(peer_id)
                from modules.keyboards import vertical_kb
                kb = vertical_kb([], nav_buttons=[("🔄 Повторить", {"cmd": "retry_generation", "section": target_section, "p_name": partner_name, "p_date": partner_date, "c_id": card_id}, KeyboardButtonColor.PRIMARY), ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)])
                await ghost_edit(bot.api, peer_id, msg, conversation_message_id=conversation_message_id, keyboard=kb)
                return

            if res_text:
                # 1. Очистка от ВСТУПЛЕНИЕ
                res_text = re.sub(r"(?i)\bВСТУПЛЕНИЕ\b", "", res_text)
                # 2. Очистка от артефактов экранирования (n/nn) и запрещенных символов
                # Сначала заменяем строковые \n на реальные переносы строк, чтобы избежать появления "n" или "nn"
                res_text = res_text.replace('\\\\n', '\n').replace('\\n', '\n')
                res_text = res_text.replace("#", "").replace("*", "").replace("|", "").replace("\\", "")

                # Чистый текст для истории и PDF (без меток и добавок чата)
                full_reading_text = re.sub(r"ID_?ТАРО:\s*\d+", "", res_text).strip()

                # 3. Программный заголовок для хиромантии и сонника
                if target_section == "palmistry":
                    if not full_reading_text.upper().startswith("ХИРОМАНТИЯ"):
                        full_reading_text = "ХИРОМАНТИЯ\n\n" + full_reading_text
                elif target_section == "dream":
                    if not full_reading_text.upper().startswith("СОННИК"):
                        full_reading_text = "СОННИК\n\n" + full_reading_text

                display_text = full_reading_text

                # Сохраняем в историю в Redis (вместо Supabase)
                titles = {
                    "sex": "Сексуальность", "money": "Богатство", "shadow": "Тень",
                    "final": "Путь", "synastry": "Синастрия", "oracle": "Оракул",
                    "antitaro": "Антитаро", "report": "Разбор", "card_of_day": "Карта дня",
                    "palmistry": "Хиромантия", "dream": "Толкование сна"
                }

                history_item = {
                    "title": titles.get(target_section, "Разбор"),
                    "date": datetime.datetime.now().strftime("%d.%m.%Y"),
                    "text": display_text,
                    "section": target_section
                }
                if target_section == "synastry" and partner_name:
                    history_item["partner_name"] = partner_name

                from cache import set_latest_reading, add_reading_to_history, get_readings_history
                await add_reading_to_history(vk_id, history_item)
                await set_latest_reading(vk_id, display_text, data=res_data if isinstance(res_data, dict) else None)

                # Получаем обновленную историю из Redis для проверки достижений
                history = await get_readings_history(vk_id)

                save_data = {}

                # Сбрасываем флаг покупки, так как услуга использована
                purchased = user.get("purchased_sections", {})
                if target_section in purchased:
                    purchased[target_section] = False
                    save_data["purchased_sections"] = purchased

                # Награда за Карту Дня
                if target_section == "card_of_day":
                    save_data["balance"] = user.get("balance", 0) + 100
                    save_data["visit_streak"] = user.get("visit_streak", 0) + 1
                    purchased["card_of_day_last_used"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    save_data["purchased_sections"] = purchased

                # latest_reading_data больше не сохраняем в Supabase

                # --- ИНКРЕМЕНТ СЧЕТЧИКОВ ПРОГРЕССА ---
                save_data["rituals_count"] = (user.get("rituals_count", 0) or 0) + 1

                if target_section == "dream":
                    save_data["dreams_analyzed_count"] = (user.get("dreams_analyzed_count", 0) or 0) + 1

                if target_section == "synastry" and partner_name and partner_date:
                    p_hash = hashlib.md5(f"{partner_name.lower().strip()}{partner_date.strip()}".encode()).hexdigest()
                    hashes = user.get("compatibility_partners_hashes", [])
                    if not isinstance(hashes, list): hashes = []
                    if p_hash not in hashes:
                        hashes.append(p_hash)
                        save_data["compatibility_partners_hashes"] = hashes
                        save_data["compatibility_partners_count"] = (user.get("compatibility_partners_count", 0) or 0) + 1
                # ------------------------------------

                await update_user(vk_id, save_data)

                async def extract_and_save_tags(v_id: int, text: str):
                    new_tags = await extract_tags(text)
                    if new_tags:
                        await update_user(v_id, {"tags": new_tags})
                        if "выход-из-кризиса" in new_tags and "свобода" in new_tags:
                            from modules.skins import unlock_skin
                            await unlock_skin(bot.api, v_id, "honest_oracle")

                asyncio.create_task(extract_and_save_tags(vk_id, res_text))

                # --- Ачивки ---
                from modules.skins import unlock_skin
                from modules.utils.logic import calculate_user_rank

                # ai_mom: 30 генераций
                if len(history) >= 30:
                    await unlock_skin(bot.api, vk_id, "ai_mom")

                # pythia: 10 снов
                dream_count = sum(1 for h in history if h.get("section") == "dream")
                if dream_count >= 10:
                    await unlock_skin(bot.api, vk_id, "pythia")

                # freud: 3 разных партнера в синастрии
                synastry_partners = {h.get("partner_name") for h in history if h.get("section") == "synastry" and h.get("partner_name")}
                if len(synastry_partners) >= 3:
                    await unlock_skin(bot.api, vk_id, "freud")

                # Уровень и ранг для дальнейших проверок
                user_for_level = {**user, **save_data} # Совмещаем текущие данные и новые для расчета
                level, _ = calculate_user_rank(user_for_level)

                # anubis: 5 уровень + все разделы
                used_sections = {h.get("section") for h in history}
                core_sections = {"sex", "money", "shadow", "final", "synastry", "palmistry", "dream", "oracle", "antitaro"}
                if level >= 5 and core_sections.issubset(used_sections):
                    await unlock_skin(bot.api, vk_id, "anubis")

                # fluffy: приглашенные друзья достигли 3 уровня
                if level >= 3 and not user.get("level_3_counted"):
                    await update_user(vk_id, {"level_3_counted": True})

                    referrer_id = purchased.get("referrer_id")
                    if referrer_id:
                        referrer = await get_user(referrer_id)
                        if referrer:
                            current_active_refs = (referrer.get("active_referrals_count", 0) or 0) + 1
                            await update_user(referrer_id, {"active_referrals_count": current_active_refs})

                            if current_active_refs >= 5:
                                await unlock_skin(bot.api, referrer_id, "fluffy")
                # --------------

                from modules.keyboards import after_pdf_kb, vertical_kb
                if target_section == "card_of_day":
                    light_kb = vertical_kb([
                        ("📜 ПОЛНЫЙ PDF-ОТЧЕТ", {"cmd": "gen_pdf", "section": target_section, "card": card_id}, KeyboardButtonColor.POSITIVE),
                        ("🔮 ГЛУБОКИЙ РАЗБОР (-50%)", {"cmd": "confirm_buy", "type": "service", "key": "oracle_upsell"}, KeyboardButtonColor.PRIMARY),
                        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
                    ])
                    kb_str = light_kb
                elif target_section == "synastry":
                    kb_str = vertical_kb([
                        ("📜 ПОЛНЫЙ PDF-ОТЧЕТ", {"cmd": "gen_pdf", "section": target_section, "card": card_id}, KeyboardButtonColor.POSITIVE),
                        ("❤️ ЕЩЕ ОДИН РАСЧЕТ", {"cmd": "use_section", "key": "synastry"}, KeyboardButtonColor.PRIMARY),
                        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
                    ])
                elif target_section == "palmistry":
                    kb_str = vertical_kb([
                        ("📜 ПОЛНЫЙ PDF-ОТЧЕТ", {"cmd": "gen_pdf", "section": target_section, "card": card_id}, KeyboardButtonColor.POSITIVE),
                        ("✨ НОВЫЙ АНАЛИЗ", {"cmd": "use_section", "key": "palmistry"}, KeyboardButtonColor.PRIMARY),
                        ("📖 ГРИМУАР", {"cmd": "profile_action", "action": "grimoire"}, KeyboardButtonColor.PRIMARY),
                        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
                    ])
                elif target_section == "dream":
                    kb_str = vertical_kb([
                        ("🌙 НОВЫЙ СОН", {"cmd": "use_section", "key": "dream"}, KeyboardButtonColor.PRIMARY),
                        ("📖 ГРИМУАР", {"cmd": "profile_action", "action": "grimoire"}, KeyboardButtonColor.PRIMARY),
                        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
                    ])
                else:
                    kb_str = after_pdf_kb(target_section, card_id)

                if target_section == "dream":
                    # Автоматическая генерация PDF для сонника
                    async def auto_gen_pdf_task(v_id, p_id, txt, s_name, u_n, b_i, char_n):
                        pdf_name = f"report_{v_id}_{s_name}.pdf"
                        from modules.utils import generate_premium_pdf, upload_pdf_to_vk, pdf_semaphore
                        import os
                        async with pdf_semaphore:
                            success = await asyncio.to_thread(
                                generate_premium_pdf,
                                user_name=u_n,
                                birth_info=b_i,
                                section_name="СОННИК",
                                text_content=txt,
                                output_filename=pdf_name,
                                card_id="uslugi/dream",
                                current_date=datetime.datetime.now().strftime("%d.%m.%Y"),
                                character_name=char_n
                            )
                        if success and os.path.exists(pdf_name):
                            doc = await upload_pdf_to_vk(bot.api, filepath=pdf_name, title=f"{s_name}.pdf", peer_id=p_id)
                            if doc:
                                await bot.api.messages.send(peer_id=p_id, message="Твой PDF-отчет по сну готов:", attachment=doc, random_id=random.getrandbits(63))

                    from modules.utils.consts import SKIN_DISPLAY_NAMES
                    char_name = SKIN_DISPLAY_NAMES.get(active_skin, "Проводник")
                    b_info = f"{birth_data.get('date')} {birth_data.get('time')} {birth_data.get('city')}"
                    asyncio.create_task(auto_gen_pdf_task(vk_id, peer_id, display_text, "dream", u_name, b_info, char_name))

                if isinstance(res_data, dict):
                    # В чат выводим сокращенную версию: Текст + Уровень активации + Аффирмации
                    # Остальное (Прогноз на 30 дней, Факты и т.д.) остается только в PDF
                    chat_text = full_reading_text

                    act_lvl = res_data.get('activation_level')
                    if act_lvl:
                        chat_text += f"\n\n⚡ УРОВЕНЬ АКТИВАЦИИ: {act_lvl}%"
                        if res_data.get('activation_comment'):
                            chat_text += f"\n{res_data.get('activation_comment')}"

                    affirmations = res_data.get('affirmations')
                    if affirmations:
                        if isinstance(affirmations, list):
                            affirmations_list = [f"- {a}" for a in affirmations]
                            affirmations_text = "\n".join(affirmations_list)
                        else:
                            affirmations_text = str(affirmations)
                        chat_text += f"\n\nТвои аффирмации:\n{affirmations_text}"

                    chat_text += "\n\n------------------\n✨ Твой сакральный отчет со всеми деталями, кодами и картой энергии готов к загрузке. Нажми на кнопку ниже, чтобы сохранить это знание навсегда."
                    display_text = chat_text

                # Финальная очистка от возможных остатков JSON-разметки если что-то пошло не так
                if display_text.strip().startswith('{') or '"text":' in display_text:
                    display_text = re.sub(r'\{.*"text":\s*', '', display_text, flags=re.DOTALL)
                    display_text = re.sub(r'",\s*"shadow_side".*', '', display_text, flags=re.DOTALL)
                    display_text = display_text.strip('"').strip()

                typing_msg_id = await stop_dynamic_typing(peer_id)

                # Сохраняем "шапку" с картой, если это был ghost-процесс
                header = ""
                if card_data:
                    header = f"🃏 {card_data.get('name')} — {card_data.get('subtitle')}\n------------------\n\n"

                # Если conversation_message_id был передан (регистрация), используем его как CMID.
                # Если нет (расклад), используем ID сообщения динамического тайпинга как MID.
                if conversation_message_id:
                    await ghost_edit(
                        bot.api,
                        peer_id,
                        header + display_text,
                        conversation_message_id=conversation_message_id,
                        keyboard=kb_str
                    )
                else:
                    await ghost_edit(
                        bot.api,
                        peer_id,
                        header + display_text,
                        message_id=typing_msg_id,
                        keyboard=kb_str
                    )
            else:
                await handle_generation_failure(vk_id, peer_id, target_section, conversation_message_id=conversation_message_id, partner_name=partner_name, partner_date=partner_date, card_id=card_id)
        finally:
            await stop_dynamic_typing(peer_id)
    except Exception as e:
        await stop_dynamic_typing(peer_id)
        logger.error(f"Ошибка: {str(e)}")
        await handle_generation_failure(vk_id, peer_id, target_section, conversation_message_id=conversation_message_id, partner_name=partner_name, partner_date=partner_date, card_id=card_id)
    finally:
        await release_lock(lock_key)

async def handle_generation_failure(vk_id: int, peer_id: int, target_section: str, conversation_message_id: int = None, partner_name: str = "", partner_date: str = "", card_id: str = ""):
    prices = {
        "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
        "synastry": 1500, "palmistry": 1200, "dream": 1000, "all": 3000, "oracle": 500, "antitaro": 500,
        "micro_insight": 100, "oracle_upsell": 250,
        "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900
    }
    price_of_service = prices.get(target_section, 0)
    user = await get_user(vk_id)
    if user and price_of_service > 0:
        # Атомарный инкремент через SQL был бы лучше, но здесь используем текущую практику проекта
        new_balance = int(user.get("balance", 0) or 0) + price_of_service
        await update_user(vk_id, {"balance": new_balance})

    msg = "🛑 КАНАЛ СВЯЗИ НЕСТАБИЛЕН\n\nЗвезды скрылись за облаками матрицы. Энергия возвращена на твой баланс. Попробуй инициировать ритуал снова."

    await stop_dynamic_typing(peer_id)

    from modules.keyboards import vertical_kb
    # Кнопка повтора с сохранением контекста
    retry_payload = {
        "cmd": "retry_generation",
        "section": target_section,
        "p_name": partner_name,
        "p_date": partner_date,
        "c_id": card_id
    }

    kb = vertical_kb([], nav_buttons=[
        ("🔄 Повторить попытку", retry_payload, KeyboardButtonColor.POSITIVE),
        ("🏠 В МЕНЮ", "main_menu", KeyboardButtonColor.SECONDARY)
    ])

    await ghost_edit(
        bot.api,
        peer_id,
        msg,
        conversation_message_id=conversation_message_id,
        keyboard=kb
    )
