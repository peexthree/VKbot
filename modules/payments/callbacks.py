import asyncio
import datetime
import json
import math
import os
import random
from loguru import logger
from vkbottle import (
    Callback, GroupEventType, Keyboard, KeyboardButtonColor, OpenLink
)
from vkbottle.bot import BotLabeler

async def safe_edit(peer_id, message, conversation_message_id=None, keyboard=None, attachment=None, **kwargs):
    """Обертка для безопасного редактирования с защитой от Flood Control."""
    # Используем ghost_edit для унификации логики и защиты от Flood Control
    await ghost_edit(
        bot.api,
        peer_id=peer_id,
        message=message,
        conversation_message_id=conversation_message_id,
        keyboard=keyboard,
        attachment=attachment,
        **kwargs
    )


from cache import acquire_lock, check_throttle, release_lock, set_fsm_state, redis_client
from cards_data import get_card_data
from database import (
    get_user, set_user_state, update_user
)
from modules.bot_init import bot
from modules.utils import (
    SKIN_ASSETS, generate_premium_pdf, get_fsm_step, get_main_keyboard,
    ghost_edit, pdf_semaphore, upload_local_photo, upload_pdf_to_vk
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
    try:
        await _message_event_handler_wrapped(event)
    except (ConnectionResetError, asyncio.TimeoutError) as e:
        logger.warning(f"Network error in message_event_handler: {e}")
    except Exception as e:
        logger.exception(f"Unhandled error in message_event_handler: {e}")

async def _message_event_handler_wrapped(event: dict, skip_lock: bool = False):
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

    # --- ФИКС ТАЙМАУТА: Отвечаем мгновенно до тяжелых операций ---
    if event_id and vk_id:
        lock_key = f"event_answered:{event_id}"
        # nx=True вернет True если ключ установлен, иначе False/None
        res = await redis_client.set(lock_key, "1", ex=30, nx=True)
        if not res:
            logger.debug(f"Event {event_id} already answered or being processed")
            return

        cmd = payload.get("cmd")
        # Специфические ответы для специальных кнопок
        if cmd == "skin_quest":
            from modules.skins import get_quest_text
            quest_text = get_quest_text(payload.get("skin"))
            await bot.api.messages.send_message_event_answer(
                event_id=event_id, user_id=vk_id, peer_id=peer_id,
                event_data=json.dumps({"type": "show_snackbar", "text": quest_text})
            )
        elif cmd == "share_click":
            from modules.skins import unlock_skin
            await unlock_skin(bot.api, vk_id, "jack_sparrow")

            card_id = payload.get("card")
            user = await get_user(vk_id)

            card_name = "Тайный Аркан"
            thesis_snippet = "Твой путь начертан звездами."

            if user:
                if card_id:
                    c_data = get_card_data(card_id)
                    card_name = c_data.get("name", card_name)

                import re
                latest_text = user.get("latest_reading_text") or ""
                if not latest_text:
                    latest_data = user.get("latest_reading_data", {})
                    if isinstance(latest_data, dict):
                        latest_text = latest_data.get("text", "")

                if latest_text:
                    # Очистка от технических заголовков
                    clean_text = re.sub(r'^(ХИРОМАНТИЯ|СОННИК|КАРТА ДНЯ|СЕКСУАЛЬНОСТЬ|БОГАТСТВО|ТЕНЬ|ПУТЬ|СИНАСТРИЯ|ОРАКУЛ|АНТИТАРО|РАЗБОР)\s+', '', latest_text, flags=re.IGNORECASE).strip()
                    # Берем первое предложение
                    sentences = re.split(r'[.!?]', clean_text)
                    if sentences:
                        thesis_snippet = sentences[0].strip()

            # 1. Отвечаем мгновенно, чтобы убрать спиннер
            await bot.api.messages.send_message_event_answer(
                event_id=event_id, user_id=vk_id, peer_id=peer_id,
                event_data=json.dumps({"type": "show_snackbar", "text": "Карточка для пересылки готова!"})
            )

            # 2. Формируем виральное сообщение
            ref_link = f"https://vk.me/club219181948?ref=result_{card_id}" if card_id else "https://vk.me/club219181948?ref=result"
            viral_text = f"Смотри, какой Аркан выпал мне в Анти-Таро: {card_name}. {thesis_snippet}\n\nПопробуй и ты: {ref_link}"

            # Загружаем картинку (карту или брендинг)
            photo_file = f"{card_id}.jpeg" if card_id and os.path.exists(os.path.join("cards", f"{card_id}.jpeg")) else "uslugi/main_menu.jpeg"
            attachment = await upload_local_photo(bot.api, photo_file, peer_id=vk_id)

            # 3. Отправляем карточку для шаринга
            await bot.api.messages.send(
                peer_id=peer_id,
                message=viral_text,
                attachment=attachment,
                random_id=random.getrandbits(63)
            )

            # 4. Отправляем инструкцию отдельным сообщением
            await bot.api.messages.send(
                peer_id=peer_id,
                message="👆 Просто перешли это сообщение своим друзьям!",
                random_id=random.getrandbits(63)
            )
        elif cmd in ["buy", "buy_skin"]:
            # Defer answering until payment logic completes (to show success/error snackbar)
            pass
        else:
            # Универсальный пустой ответ для всех остальных нажатий
            try:
                await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=vk_id, peer_id=peer_id)
            except Exception as e:
                logger.warning(f"Could not answer event {event_id}: {e}")
    elif event_id:
        logger.warning(f"Event {event_id} received without vk_id, cannot remove spinner")

    if not vk_id: return

    if not skip_lock:
        if payload.get("cmd") not in ["profile_action", "main_menu", "services_menu", "profile_menu"]:
            if await check_throttle(vk_id):
                return

        if not await acquire_lock(vk_id, ttl=5):
            logger.warning(f"Could not acquire lock for vk_id={vk_id} in message_event_handler")
            return
    try:
        if not vk_id or not payload: return
        cmd = payload.get("cmd")

        # Трекинг статистики
        user_for_stats = await get_user(vk_id)
        if user_for_stats:
            p_stats = user_for_stats.get("purchased_sections", {})
            p_stats["stats_clicks"] = p_stats.get("stats_clicks", 0) + 1

            # Время в интерфейсе (активность)
            now_stats = datetime.datetime.now(datetime.timezone.utc)
            last_stats_at_str = p_stats.get("stats_last_action_at")
            if last_stats_at_str:
                last_stats_at = datetime.datetime.fromisoformat(last_stats_at_str.replace('Z', '+00:00'))
                diff_stats = (now_stats - last_stats_at).total_seconds()
                # Если прошло меньше 10 минут, считаем это одной сессией
                if diff_stats < 600:
                    p_stats["stats_total_seconds"] = p_stats.get("stats_total_seconds", 0) + diff_stats

            p_stats["stats_last_action_at"] = now_stats.isoformat()
            await update_user(vk_id, {"purchased_sections": p_stats})

        if cmd in ["admin_cmd", "admin_nav", "admin_user_op"]:
            await process_admin_cmd(vk_id, peer_id, payload, conversation_message_id=obj.get("conversation_message_id"))
            return
        elif cmd == "admin_cmd_cancel":
            await set_fsm_state(vk_id, "")
            await show_admin_console(peer_id)
            return

        logger.info(f"message_event_handler triggered by vk_id={vk_id}, cmd={cmd}")

        if cmd == "retry_registration":
            await set_user_state(vk_id, json.dumps({"step": "waiting_birth_date", "conv_id": obj.get("conversation_message_id")}))
            await safe_edit(peer_id=peer_id, message="Понял. Давай попробуем еще раз. Напиши свою ДАТУ рождения (например, 15.04.1990):", conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "edit_onboarding_data":
            await set_user_state(vk_id, json.dumps({"step": "waiting_birth_date", "conv_id": obj.get("conversation_message_id")}))
            await safe_edit(peer_id=peer_id, message="Хорошо, давай начнем сначала. Напиши свою ДАТУ рождения (например, 15.04.1990):", conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "confirm_registration":
            state_dict = await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "confirm_data": return
            date, time, city = state_dict.get("date"), state_dict.get("time"), state_dict.get("city")
            original_intent = state_dict.get("original_intent")

            await set_user_state(vk_id, "")
            await safe_edit(peer_id=peer_id, message="✦ СИНХРОНИЗАЦИЯ С МАТРИЦЕЙ...", conversation_message_id=obj.get("conversation_message_id"))

            # Сохраняем в Redis на 24 часа
            from cache import set_temp_birth_data
            await set_temp_birth_data(vk_id, {
                "date": date,
                "time": time,
                "city": city
            })

            user = await get_user(vk_id)
            updates = {
                "birth_date": date,
                "birth_time": time,
                "birth_city": city,
                "is_registered": True
            }

            # Начисляем приветственный бонус если еще не получал
            if user and not user.get("welcome_bonus_received"):
                updates["balance"] = (user.get("balance", 0) or 0) + 700
                updates["welcome_bonus_received"] = True

            # Сохраняем всё одним запросом в Supabase
            await update_user(vk_id, updates)

            if date and time and city:
                from modules.skins import unlock_skin
                await unlock_skin(bot.api, vk_id, "cleopatra")

            # РЕЗОЛВ ОРИГИНАЛЬНОГО НАМЕРЕНИЯ
            if original_intent:
                oi_cmd = original_intent.get("cmd")
                if oi_cmd == "buy":
                    # Рекурсивно вызываем обработчик нажатия кнопки buy
                    event_for_oi = event.copy()
                    event_for_oi["object"]["payload"] = original_intent
                    return await _message_event_handler_wrapped(event_for_oi, skip_lock=True)
                elif oi_cmd == "process_payment_and_generate":
                    return await process_payment_and_generate(vk_id, original_intent.get("section"))
                elif oi_cmd == "execute_generation":
                    return await execute_generation(
                        vk_id, peer_id,
                        original_intent.get("target_section"),
                        original_intent.get("partner_name"),
                        original_intent.get("partner_date"),
                        card_id=original_intent.get("card_id"),
                        card_data=original_intent.get("card_data"),
                        conversation_message_id=obj.get("conversation_message_id")
                    )

            # Если мы пришли сюда из процесса покупки (старый формат), переходим к сдвигу колоды
            if target_section := state_dict.get("target_section"):
                # Сохраняем остальные метаданные при переходе к сдвигу
                state_dict["step"] = "global_cut"
                await set_user_state(vk_id, json.dumps(state_dict))
                kb = Keyboard(inline=True).add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
                await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="✨ ДАННЫЕ ПРИНЯТЫ. ТЕПЕРЬ ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ.\n\nЖми кнопку ниже.", keyboard=kb.get_json())
                return

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
                        await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="ДЛЯ АНАЛИЗА СОЮЗА НАПИШИ ИМЯ ПАРТНЕРА:")
                        return
                    if target_section == "dream":
                        await set_user_state(vk_id, json.dumps({"step": "waiting_dream_text"}))
                        msg = (
                            "✅ Оплата прошла.\n\n"
                            "Расскажи мне свой сон подробным текстом.\n\n"
                            "Можно добавить:\n"
                            "- Когда приснился (дата/время)\n"
                            "- Настроение после пробуждения\n"
                            "- Любые важные детали\n\n"
                            "Чем подробнее опишешь - тем точнее будет разбор."
                        )
                        await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message=msg)
                        return
                    if target_section == "palmistry":
                        await set_user_state(vk_id, json.dumps({"step": "waiting_palmistry_photos"}))
                        msg = (
                            "✨ ДЛЯ НОВОГО АНАЛИЗА ПРИШЛИ ДВЕ ФОТОГРАФИИ ЛАДОНЕЙ:\n\n"
                            "• Левая ладонь\n"
                            "• Правая ладонь\n\n"
                            "Убедись, что линии четко видны."
                        )
                        await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message=msg)
                        return
                    if target_section == "oracle":
                        # We need to trigger the oracle question handler
                        await set_user_state(vk_id, json.dumps({"step": "waiting_oracle_question"}))
                        await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="НАПИШИ СВОЙ ВОПРОС СУДЬБЕ:")
                        return

                    await set_user_state(vk_id, json.dumps({"step": "global_cut", "target_section": target_section}))
                    kb = Keyboard(inline=True).add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
                    await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json())
                else:
                    # Если доступа нет, показываем карточку услуги в каталоге
                    await show_services(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"), is_catalog=True, target_key=target_section)
        elif cmd == "main_menu":
            from database import add_event
            asyncio.create_task(add_event(vk_id, "menu_open"))
            user = await get_user(vk_id)
            if not user: return

            # Ежедневный бонус при каждом открытии меню
            from modules.utils.logic import check_and_give_daily_bonus
            await check_and_give_daily_bonus(vk_id, user, peer_id)

            # Сбрасываем стейты (в т.ч. поддержку)
            await set_user_state(vk_id, "")

            from modules.keyboards import main_menu_kb
            kb_json = main_menu_kb(vk_id, user)

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

            att = await upload_local_photo(bot.api, "uslugi/main_menu.jpeg", peer_id=vk_id)

            await ghost_edit(bot.api, peer_id, message=main_menu_text, keyboard=kb_json, attachment=att, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "card_of_day_menu":
            from database import add_event
            asyncio.create_task(add_event(vk_id, "daily_card_view"))
            await card_of_day_logic(vk_id, peer_id, skip_lock=True, event_id=event_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "services_menu": await show_services(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"), filter_val=payload.get("filter"), is_catalog=False)
        elif cmd == "profile_menu":
            from modules.profile.views import show_profile_logic
            await show_profile_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "natal_chart_menu":
            user = await get_user(vk_id)
            if not user: return
            from modules.keyboards import get_natal_chart_inline_keyboard
            kb_json = get_natal_chart_inline_keyboard(user.get("purchased_sections", {}))
            att = await upload_local_photo(bot.api, "uslugi/services.jpeg", peer_id=vk_id)
            await ghost_edit(bot.api, peer_id, "🔮 ТВОЯ НАТАЛЬНАЯ КАРТА\n\nВыбери раздел для глубокого погружения. Каждый разбор можно получить один раз.", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb_json, attachment=att)
        elif cmd == "history_menu":
            from database import add_event
            asyncio.create_task(add_event(vk_id, "history_open"))
            from modules.profile.views import show_history_logic
            await show_history_logic(vk_id=vk_id, peer_id=peer_id, page=payload.get("page", 0), skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
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
        elif cmd == "service_page": await show_services(vk_id, peer_id, payload.get("idx", 0), edit_msg_id=obj.get("conversation_message_id"), filter_val=payload.get("filter"), is_catalog=True)
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
                await bot.api.messages.send(peer_id=peer_id, message="Текст разбора не найден. Сгенерируйте разбор заново.", random_id=random.getrandbits(63))
                return
            await bot.api.messages.send(peer_id=peer_id, message="Создаю PDF-файл, подожди секунду...", random_id=random.getrandbits(63))
            pdf_name = f"report_{vk_id}_{section}.pdf"

            # Берем данные рождения из Redis
            from cache import get_temp_birth_data
            temp_birth = await get_temp_birth_data(vk_id) or {}
            b_info = f"{temp_birth.get('date', '')} {temp_birth.get('time', '')} {temp_birth.get('city', '')}"
            u_name = user.get("first_name") or user.get("purchased_sections", {}).get("first_name", "Адепт")
            card_data = get_card_data(card_id) if card_id else {}
            current_date_str = datetime.datetime.now().strftime("%d.%m.%Y")

            from modules.utils.consts import SKIN_DISPLAY_NAMES
            active_skin = user.get("active_skin", "olesya")
            char_name = SKIN_DISPLAY_NAMES.get(active_skin, "Проводник")

            async with pdf_semaphore:
                success = await asyncio.to_thread(
                    generate_premium_pdf,
                    user_name=u_name,
                    birth_info=b_info,
                    section_name=section.upper(),
                    text_content=latest_data.get("text", ""),
                    output_filename=pdf_name,
                    card_id=card_id,
                    advice_content="",
                    card_name=card_data.get("name"),
                    card_description=card_data.get("description"),
                    shadow_side=latest_data.get("shadow_side", ""),
                    activation_level=latest_data.get("activation_level") if section != "palmistry" else None,
                    activation_comment=latest_data.get("activation_comment", ""),
                    affirmations=latest_data.get("affirmations", ""),
                    next_activation_date=latest_data.get("next_activation_date", ""),
                    thirty_day_forecast=latest_data.get("thirty_day_forecast", ""),
                    activation_recommendations=latest_data.get("activation_recommendations", ""),
                    star_code=latest_data.get("star_code", ""),
                    energy_map=latest_data.get("energy_map", ""),
                    current_date=current_date_str,
                    palm_photos=latest_data.get("palm_photos"),
                    interesting_facts=latest_data.get("interesting_facts", ""),
                    character_name=char_name
                )
            if success and os.path.exists(pdf_name):
                try:
                    doc = await upload_pdf_to_vk(bot.api, filepath=pdf_name, title=f"{section}.pdf", peer_id=peer_id)
                    if not doc:
                        await bot.api.messages.send(peer_id=peer_id, message="Ошибка при загрузке PDF в систему ВК. Попробуйте позже.", random_id=random.getrandbits(63))
                        return

                    from modules.keyboards import post_pdf_kb
                    kb = post_pdf_kb(section, card=card_id)
                    await bot.api.messages.send(peer_id=peer_id, message="Твой PDF-файл готов. Ты можешь сохранить его или поделиться с друзьями:", attachment=doc, random_id=random.getrandbits(63), keyboard=kb)

                finally:
                    if os.path.exists(pdf_name): await asyncio.to_thread(os.remove, pdf_name)
            else: await bot.api.messages.send(peer_id=peer_id, message="Ошибка при создании PDF. Пожалуйста, попробуйте позже.", random_id=random.getrandbits(63))
        elif cmd == "profile_action":
            action, conv_id = payload.get("action"), obj.get("conversation_message_id")
            if action == "settings": await settings_handler(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "advanced_settings":
                from modules.profile.handlers import show_advanced_settings
                await show_advanced_settings(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=conv_id)
            elif action == "change_data":
                await set_user_state(vk_id, json.dumps({"step": "waiting_birth_date", "conv_id": conv_id}))
                kb = Keyboard(inline=True).add(Callback("ОТМЕНА", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.NEGATIVE)
                att = await upload_local_photo(bot.api, "uslugi/settings.jpeg", peer_id=vk_id)
                await ghost_edit(bot.api, peer_id, conversation_message_id=conv_id, message="Для калибровки звездного пути напиши свою ДАТУ рождения (например, 15.04.1990):", keyboard=kb.get_json(), attachment=att)
            elif action == "change_skin": await settings_choose_character(vk_id=vk_id, peer_id=peer_id, skip_lock=True, edit_msg_id=conv_id)
            elif action == "cancel_sub":
                user = await get_user(vk_id)
                purchased = user.get("purchased_sections", {})
                purchased["whisper_muted"] = True
                await update_user(vk_id, {"purchased_sections": purchased})
                from modules.keyboards import settings_menu_kb
                await safe_edit(peer_id=peer_id, conversation_message_id=conv_id, message="Шепот звезд успешно отключен. Ты больше не будешь получать ежедневные послания, но доступ к услугам подписки сохранен.", keyboard=settings_menu_kb(vk_id, is_muted=True))
            elif action == "resume_sub":
                user = await get_user(vk_id)
                purchased = user.get("purchased_sections", {})
                purchased["whisper_muted"] = False
                await update_user(vk_id, {"purchased_sections": purchased})
                from modules.keyboards import settings_menu_kb
                await safe_edit(peer_id=peer_id, conversation_message_id=conv_id, message="Шепот звезд снова активен! Завтра ты получишь новое послание.", keyboard=settings_menu_kb(vk_id, is_muted=False))
            elif action == "reset_account":
                await set_user_state(vk_id, json.dumps({"step": "waiting_reset_confirm"}))
                kb = Keyboard(inline=True).add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE).row().add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
                att = await upload_local_photo(bot.api, "uslugi/settings.jpeg", peer_id=vk_id)
                await ghost_edit(bot.api, peer_id, conversation_message_id=conv_id, message="⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс в системе. Вы уверены?", keyboard=kb.get_json(), attachment=att)
            elif action == "confirm_reset":
                # Очищаем только историю и теги
                await update_user(vk_id, {
                    "readings_history": [],
                    "tags": [],
                    "latest_reading_text": None,
                    "latest_reading_data": {},
                    "core_profile": ""
                })
                # Удаляем данные из Redis
                from cache import delete_temp_birth_data
                await delete_temp_birth_data(vk_id)
                await set_user_state(vk_id, "")
                await safe_edit(peer_id=peer_id, conversation_message_id=conv_id, message="Твои личные данные и история полностью стерты. Твой путь чист, но сила звезд (баланс) осталась с тобой.")
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
                await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Введи Теневой Шифр, который тебе передал другой адепт:", keyboard=kb.get_json())
            elif action == "cancel_seal":
                await set_user_state(vk_id, "")
                await syndicate_dashboard_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True)
        elif cmd == "hall_of_prophets":
            from modules.profile.settings import settings_choose_character_logic
            await settings_choose_character_logic(vk_id, peer_id, skip_lock=True, idx=0, edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "skins_page":
            from modules.profile.settings import settings_choose_character_logic
            await settings_choose_character_logic(vk_id, peer_id, skip_lock=True, idx=payload.get("page", 0), edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "skin_quest":
            return # Уже обработано в начале
        elif cmd == "share_click":
            return # Уже обработано в начале
        elif cmd == "buy":
            buy_type, key = payload.get("type"), payload.get("key")
            prices = {
                "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
                "synastry": 1500, "palmistry": 1200, "dream": 1000, "all": 3000, "oracle": 500, "antitaro": 500,
                "oracle_upsell": 250,
                "micro_insight": 100,
                "destiny_card": 1500,
                "destiny_card_update": 1000,
                "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900,
                "topup_5000": 400, "topup_10000": 750, "topup_50000": 3500
            }
            amount_needed = prices.get(key)
            if not amount_needed: return

            # ПРОВЕРКА ДАТЫ РОЖДЕНИЯ ПЕРЕД ПОКУПКОЙ УСЛУГ (кроме пополнений и тарифов)
            if buy_type == "service" or key in ["destiny_card", "destiny_card_update"]:
                from cache import get_temp_birth_data
                birth_data = await get_temp_birth_data(vk_id)
                if not birth_data:
                    state_data = {
                        "step": "waiting_birth_date",
                        "conv_id": obj.get("conversation_message_id"),
                        "original_intent": {"cmd": "buy", "type": buy_type, "key": key}
                    }
                    await set_user_state(vk_id, json.dumps(state_data))
                    await safe_edit(
                        peer_id=peer_id,
                        conversation_message_id=obj.get("conversation_message_id"),
                        message="🔮 ДЛЯ АКТИВАЦИИ ПОТОКА МНЕ НУЖНА ТВОЯ ДАТА РОЖДЕНИЯ\n\nЧтобы я могла настроиться на твою энергию и провести ритуал, шепни мне дату своего рождения (например, 15.04.1990):"
                    )
                    return

            user = await get_user(vk_id)
            if not user: return
            balance = int(user.get("balance", 0) or 0)

            # Process dynamically calculated discounts via abandoned cart payload
            if buy_type in ["abandoned_10", "abandoned_15"]:
                amount_needed = int(amount_needed * (0.90 if buy_type == "abandoned_10" else 0.85))
                buy_type = "service" if key in ["sex", "money", "shadow", "final", "synastry", "all", "oracle", "antitaro", "micro_insight"] else "tariff" if key.startswith("tariff_") else "topup"

            # Для прямых пополнений сразу ведем на оплату
            if buy_type == "topup" or key.startswith("topup_"):
                rubles = amount_needed

                # Трекинг потраченных рублей
                p = user.get("purchased_sections", {})
                p["stats_total_rubles"] = p.get("stats_total_rubles", 0) + rubles
                await update_user(vk_id, {"purchased_sections": p})
                # Определяем количество энергии по ключу
                energy_map = {"topup_5000": 5000, "topup_10000": 10000, "topup_50000": 50000}
                energy_amount = energy_map.get(key, rubles * 10)

                # Трекинг брошенной корзины
                p = user.get("purchased_sections", {})
                p["last_cart_item"] = key
                p["last_cart_stage"] = 0
                p["last_cart_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                await update_user(vk_id, {"purchased_sections": p})

                from modules.payments.yookassa import create_yookassa_payment
                payment_url = await create_yookassa_payment(
                    amount=rubles,
                    description=f"Пополнение баланса: {energy_amount} энергии",
                    user_id=vk_id
                )

                if payment_url:
                    kb = Keyboard(inline=True).add(OpenLink(link=payment_url, label="💳 ОПЛАТИТЬ КАРТОЙ"))
                    kb.row().add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
                    await ghost_edit(bot.api, peer_id, f"💳 ПОПОЛНЕНИЕ БАЛАНСА\n\nВы выбрали пакет: {energy_amount} ✨\nСтоимость: {rubles} RUB\n\nНажмите кнопку ниже для перехода к оплате.", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
                else:
                    await bot.api.messages.send(peer_id=peer_id, message="Ошибка при создании платежа. Попробуйте позже.", random_id=random.getrandbits(63))
                return

            if balance >= amount_needed:
                new_balance = balance - amount_needed
                await update_user(vk_id, {"balance": new_balance})

                if key == "oracle_upsell": key = "oracle" # resolve the upsell back to its base service

                if key in ["destiny_card", "destiny_card_update"]:
                    from modules.tarot.destiny import generate_destiny_card_logic
                    await generate_destiny_card_logic(
                        vk_id, peer_id,
                        conversation_message_id=obj.get("conversation_message_id"),
                        is_update=(key == "destiny_card_update")
                    )
                    return

                if buy_type == "skin":
                    from modules.utils.consts import SKIN_DISPLAY_NAMES
                    char_name = SKIN_DISPLAY_NAMES.get(key, "Проводник")
                    await process_skin_action_logic(vk_id, peer_id, skip_lock=True, payload={"cmd": "set_skin", "skin": key}, conversation_message_id=obj.get("conversation_message_id"))
                    if event_id:
                        await bot.api.messages.send_message_event_answer(
                            event_id=event_id, user_id=vk_id, peer_id=peer_id,
                            event_data=json.dumps({"type": "show_snackbar", "text": f"🎭 {char_name} теперь твой Проводник! ✨"})
                        )
                    return

                if buy_type == "service":
                    from database import add_event
                    asyncio.create_task(add_event(vk_id, "paid_feature_used", {"service": key}))
                    await process_payment_and_generate(vk_id, key)
                    if event_id:
                        await bot.api.messages.send_message_event_answer(
                            event_id=event_id, user_id=vk_id, peer_id=peer_id,
                            event_data=json.dumps({"type": "show_snackbar", "text": f"✨ Списано {amount_needed} энергии. Ритуал начат!"})
                        )
                elif buy_type == "tariff":
                    days = 7 if key == "tariff_1" else 30
                    new_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
                    updates = {"transit_sub_expires_at": new_expires.isoformat()}
                    if key == "tariff_vip":
                        p = user.get("purchased_sections", {})
                        for s in ["sex", "money", "shadow", "final"]: p[s] = True
                        updates["purchased_sections"], updates["has_full_chart"] = p, True
                    await update_user(vk_id, updates)

                    from modules.skins import unlock_skin
                    await unlock_skin(bot.api, vk_id, "saint_germain")

                    if event_id:
                        await bot.api.messages.send_message_event_answer(
                            event_id=event_id, user_id=vk_id, peer_id=peer_id,
                            event_data=json.dumps({"type": "show_snackbar", "text": f"✨ Транзит активирован! Баланс: {new_balance} ✨"})
                        )
                    else:
                        await bot.api.messages.send(peer_id=peer_id, message=f"ОПЛАТА УСПЕШНА.\n\nТранзит продлен до {new_expires.strftime('%d.%m.%Y %H:%M')}.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {new_balance} Энергии звезд.", random_id=random.getrandbits(63), keyboard=get_main_keyboard(vk_id))
            else:
                if event_id:
                    await bot.api.messages.send_message_event_answer(
                        event_id=event_id, user_id=vk_id, peer_id=peer_id,
                        event_data=json.dumps({"type": "show_snackbar", "text": "🛑 Недостаточно энергии для активации!"})
                    )
                diff_rubles = math.ceil((amount_needed - balance) / 10)
                from modules.payments.yookassa import create_yookassa_payment
                payment_url = await create_yookassa_payment(
                    amount=diff_rubles,
                    description=f"Доплата за услугу {key}",
                    user_id=vk_id
                )

                kb = Keyboard(inline=True)
                if payment_url:
                    kb.add(OpenLink(link=payment_url, label="💳 ОПЛАТИТЬ КАРТОЙ")).row()

                kb.add(Callback("🎁 ПОЗВАТЬ ДРУГА (+500 ✨)", payload={"cmd": "get_referral"}), color=KeyboardButtonColor.POSITIVE).row()
                kb.add(OpenLink(link="https://vk.com/@taroanti-oferta", label="📜 ПУБЛИЧНАЯ ОФЕРТА"))
                await ghost_edit(bot.api, peer_id=peer_id, message=f"🛑 НЕДОСТАТОЧНО ЭНЕРГИИ.\nТвой баланс: {balance} ✨. Требуется: {amount_needed} ✨.\nСистема не может вскрыть этот слой матрицы.\n\nОплати недостающие {amount_needed - balance} энергии за {diff_rubles} RUB или позови друга, чтобы получить 500 ✨ бесплатно.\n\nСовершая оплату, вы принимаете условия публичной оферты: https://vk.com/@taroanti-oferta", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
        elif cmd == "get_referral":
            from modules.profile.views import get_seal_logic
            await get_seal_logic(vk_id=vk_id, peer_id=peer_id, skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "grimoire_page": await show_grimoire_page(vk_id, peer_id, payload.get("page", 0), skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "dream_interpret_start":
            user = await get_user(vk_id)
            if user:
                purchased = user.get("purchased_sections", {})
                if purchased.get("dream"):
                    await set_user_state(vk_id, json.dumps({"step": "waiting_dream_text"}))
                    msg = (
                        "Расскажи мне свой сон подробным текстом.\n\n"
                        "Можно добавить:\n"
                        "- Когда приснился (дата/время)\n"
                        "- Настроение после пробуждения\n"
                        "- Любые важные детали\n\n"
                        "Чем подробнее опишешь - тем точнее будет разбор."
                    )
                    await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message=msg)
                else:
                    await show_services(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"), is_catalog=True, target_key="dream")

        elif cmd == "view_card": await view_card_direct(vk_id, peer_id, str(payload.get("id")), skip_lock=True, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "support":
            from modules.support import support_handler_logic
            await support_handler_logic(vk_id, peer_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "admin_reply_start":
            from modules.support import admin_reply_start_logic
            await admin_reply_start_logic(vk_id, payload.get("user_id"))
        elif cmd == "balance":
            await show_tariffs(vk_id, peer_id, 0, edit_msg_id=obj.get("conversation_message_id"))
        elif cmd == "destiny_card_info":
            from modules.tarot.destiny import destiny_card_info_logic
            await destiny_card_info_logic(vk_id, peer_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "buy_destiny_card":
            from modules.tarot.destiny import generate_destiny_card_logic
            await generate_destiny_card_logic(vk_id, peer_id, conversation_message_id=obj.get("conversation_message_id"))
        elif cmd == "confirm_buy":
            buy_type, key = payload.get("type"), payload.get("key")
            prices = {
                "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
                "synastry": 1500, "palmistry": 1200, "dream": 1000, "all": 3000, "oracle": 500, "antitaro": 500,
                "oracle_upsell": 250, "micro_insight": 100,
                "destiny_card": 1500, "destiny_card_update": 1000,
                "skin": 1500,
                "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900
            }
            cost = prices.get(key, 0)
            from modules.keyboards import confirmation_kb
            kb = confirmation_kb({"cmd": "buy", "type": buy_type, "key": key}, cost)
            await safe_edit(peer_id=peer_id,
                conversation_message_id=obj.get("conversation_message_id"),
                message=f"❓ ПОДТВЕРЖДЕНИЕ ПОКУПКИ\n\nВы уверены, что хотите приобрести эту услугу?\nБудет списано: {cost} ✨",
                keyboard=kb
            )
        elif cmd == "show_offer":
            offer_url = "https://vk.com/@taroanti-oferta"
            await bot.api.messages.send(peer_id=peer_id, message=f"📜 ПУБЛИЧНАЯ ОФЕРТА:\n{offer_url}", random_id=random.getrandbits(63))
        elif cmd == "skip_birth_time":
            state_dict = await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "waiting_birth_time": return
            state_dict.update({"step": "waiting_birth_city", "time": "12:00"})
            await set_user_state(vk_id, json.dumps(state_dict))
            await safe_edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="🕯 Время скрыто, но это не помешает нам. И последний штрих — в каком ГОРОДЕ ты увидел свой первый звездный свет?")
        elif cmd == "oracle_cut":
            state = await get_fsm_step(vk_id)
            if not state or state.get("step") != "oracle_cut": return
            pool = list(range(0, 78))
            random.shuffle(pool)
            pool = pool[:10]
            await set_user_state(vk_id, json.dumps({"step": "oracle_draw", "question": state.get("question", ""), "drawn_cards": [], "pool": pool}))
            kb = Keyboard(inline=True)
            for _i, cid in enumerate(pool):
                kb.add(Callback("🎴", payload={"oracle_card": cid}))
                if (_i + 1) % 2 == 0 and (_i + 1) < len(pool):
                    kb.row()
            await safe_edit(peer_id=peer_id, message="✨ ШАГ 3 ИЗ 3: ТВОЙ ВЫБОР ✨\nПрислушайся к интуиции и выбери 3 карты, которые откликаются тебе сейчас.", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
        elif cmd == "global_cut":
            target = payload.get("target")
            if target: await set_user_state(vk_id, json.dumps({"step": "global_cut", "target_section": target}))
            kb = Keyboard(inline=True)
            # 2x5 grid to fit within 6 rows limit
            for _i in range(10):
                kb.add(Callback("🎴", payload={"cmd": "global_draw"}), color=KeyboardButtonColor.SECONDARY)
                if (_i + 1) % 2 == 0 and _i < 9:
                    kb.row()
            await safe_edit(peer_id=peer_id, message="Выбери карту из разложенных:", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
        elif cmd == "global_draw":
            # 1. Сразу убираем кнопки и показываем статус
            conv_id = obj.get("conversation_message_id")
            await safe_edit(peer_id=peer_id, conversation_message_id=conv_id, message="✦ КАРТА ВЫБРАНА. ИНИЦИАЦИЯ...", keyboard=Keyboard(inline=True).get_json())

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

            from modules.utils.consts import SKIN_DISPLAY_NAMES
            p_display = SKIN_DISPLAY_NAMES.get(active_skin, "Проводник")

            # 3. Обновляем ТЕКУЩЕЕ сообщение, добавляя информацию о карте и картинки
            ritual_text = (
                f"🔮 Проводник: {p_display}\n"
                f"🃏 Твоя карта: {card_data.get('name')} — {card_data.get('subtitle')}\n"
                f"📖 Значение: {card_data.get('description')}\n\n"
                "------------------\n"
                "✦ СЧИТЫВАЮ ПОТОК ДЛЯ ПЕРСОНАЛИЗИРОВАННОГО РАЗБОРА..."
            )

            await safe_edit(peer_id=peer_id,
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

                # Фильтруем оставшиеся карты
                remaining = [c for c in pool if c not in drawn]

                kb, b_cnt = Keyboard(inline=True), 0
                for c_id in remaining:
                    kb.add(Callback("🎴", payload={"oracle_card": c_id}))
                    b_cnt += 1
                    if b_cnt % 2 == 0 and b_cnt < len(remaining):
                        kb.row()
                await safe_edit(peer_id=peer_id, message=f"Выбрано: {len(drawn)}/3...", conversation_message_id=obj.get("conversation_message_id"), keyboard=kb.get_json())
            else:
                await set_user_state(vk_id, "")
                conv_id = obj.get("conversation_message_id")
                await safe_edit(peer_id=peer_id, message="Выбрано: 3/3. Карты собраны.", conversation_message_id=conv_id, keyboard=Keyboard(inline=True).get_json())
                asyncio.create_task(process_oracle_final(vk_id, state_dict.get("question", ""), drawn, conversation_message_id=conv_id))
    finally: await release_lock(vk_id)
