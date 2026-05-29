import asyncio
import datetime
import json
import re
from loguru import logger
from vkbottle import Keyboard, Callback, KeyboardButtonColor
from database import get_user, update_user, set_user_state
from modules.bot_init import bot
from ai_service import generate_section, extract_tags
from modules.utils import (
    get_main_keyboard, ghost_edit,
    start_dynamic_typing, stop_dynamic_typing
)
from cache import acquire_lock, release_lock

async def process_payment_and_generate(vk_id: int, section: str):
    lock_key = f"process_payment_and_generate:{vk_id}"
    if not await acquire_lock(lock_key, ttl=300): return
    try:
        user = await get_user(vk_id)
        if not user: return

        if section == "micro_insight":
            active_skin = user.get("active_skin", "olesya")
            from ai_service import generate_text
            prompt = (
                f"Пользователь купил микро-инсайт. Его данные: {user.get('birth_date')} {user.get('birth_city')}. "
                f"Теги: {user.get('tags', [])}. "
                f"Дай ОДИН короткий, дерзкий и точный совет или предсказание на ближайший час. "
                f"Стиль: {active_skin}. Максимум 2 предложения. Без жирного шрифта."
            )
            insight = await generate_text(prompt, skin=active_skin)
            from modules.keyboards import get_main_reply_keyboard
            await bot.api.messages.send(
                peer_id=vk_id,
                message=f"✦ ШЕПОТ МАТРИЦЫ ✦\n\n{insight}",
                random_id=0,
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
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. Все Врата открыты.", random_id=0, keyboard=get_main_keyboard(vk_id))
        elif section == "oracle":
            purchased["oracle_access"] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, '{"step": "waiting_oracle_question"}')
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. НАПИШИ СВОЙ ВОПРОС СУДЬБЕ.", random_id=0, keyboard=get_main_keyboard(vk_id))
            return
        elif section == "synastry":
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, '{"step": "waiting_synastry_name"}')
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА. НАПИШИ ИМЯ ПАРТНЕРА.", random_id=0, keyboard=get_main_keyboard(vk_id))
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
            await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0, keyboard=get_main_keyboard(vk_id))
            return
        else:
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            # Призрачный интерфейс: удаляем старое и шлем подтверждение
            from modules.utils import delete_bot_message, get_last_bot_msg, set_last_bot_msg
            last_mid = await get_last_bot_msg(vk_id)
            if last_mid:
                await delete_bot_message(bot.api, vk_id, mid=last_mid)

            msg_id = await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.", random_id=0, keyboard=get_main_keyboard(vk_id))
            await set_last_bot_msg(vk_id, msg_id)

        await set_user_state(vk_id, f'{{"step": "global_cut", "target_section": "{section}"}}')
        kb = Keyboard(inline=True)
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)
        await bot.api.messages.send(peer_id=vk_id, message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json(), random_id=0)
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

        # Если мы не редактируем старое сообщение, то dynamic_typing создаст новое
        typing_task = await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)

        try:
            p = user.get("purchased_sections", {})
            active_skin = user.get("active_skin", "olesya")
            tags = user.get("tags", [])

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

            res_data = await generate_section(
                target_section, user.get("birth_date"), user.get("birth_time"),
                user.get("birth_city"), user.get("core_profile", ""),
                u_name, u_sex,
                partner_name=partner_name, partner_date=partner_date, skin=active_skin,
                card_id=card_id, card_data=card_data, tags=tags, return_json=True,
                current_date=current_date_str,
                image_urls=image_urls
            )

            res_text = res_data.get("text", "") if isinstance(res_data, dict) else res_data

            if res_text:
                # 1. Очистка от ВСТУПЛЕНИЕ
                res_text = re.sub(r"(?i)\bВСТУПЛЕНИЕ\b", "", res_text)
                # 2. Очистка от запрещенных символов
                res_text = res_text.replace("#", "").replace("*", "").replace("|", "").replace("\\", "")

                display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", res_text).strip()

                # 3. Программный заголовок для хиромантии
                if target_section == "palmistry":
                    if not display_text.upper().startswith("ХИРОМАНТИЯ"):
                        display_text = "ХИРОМАНТИЯ\n\n" + display_text

                # Сохраняем в историю
                history = user.get("readings_history", [])
                if not isinstance(history, list): history = []

                titles = {
                    "sex": "Сексуальность", "money": "Богатство", "shadow": "Тень",
                    "final": "Путь", "synastry": "Синастрия", "oracle": "Оракул",
                    "antitaro": "Антитаро", "report": "Разбор", "card_of_day": "Карта дня",
                    "palmistry": "Хиромантия"
                }

                history.append({
                    "title": titles.get(target_section, "Разбор"),
                    "date": datetime.datetime.now().strftime("%d.%m.%Y"),
                    "text": display_text,
                    "section": target_section
                })

                save_data = {
                    "latest_reading_text": display_text,
                    "readings_history": history
                }

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

                if isinstance(res_data, dict):
                    res_data["text"] = display_text
                    if image_urls:
                        res_data["palm_photos"] = image_urls
                    save_data["latest_reading_data"] = res_data
                else:
                    save_data["latest_reading_data"] = {"text": display_text}

                await update_user(vk_id, save_data)

                async def extract_and_save_tags(v_id: int, text: str):
                    new_tags = await extract_tags(text)
                    if new_tags:
                        await update_user(v_id, {"tags": new_tags})

                asyncio.create_task(extract_and_save_tags(vk_id, res_text))

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
                else:
                    kb_str = after_pdf_kb(target_section, card_id)

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

                    display_text += "\n\n------------------\n✨ Твой сакральный отчет со всеми деталями, кодами и картой энергии готов к загрузке. Нажми на кнопку ниже, чтобы сохранить это знание навсегда."

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
                await handle_generation_failure(vk_id, peer_id, target_section, conversation_message_id=conversation_message_id)
        finally:
            await stop_dynamic_typing(peer_id)
    except Exception as e:
        await stop_dynamic_typing(peer_id)
        logger.error(f"Ошибка: {str(e)}")
        await handle_generation_failure(vk_id, peer_id, target_section, conversation_message_id=conversation_message_id)
    finally:
        await release_lock(lock_key)

async def handle_generation_failure(vk_id: int, peer_id: int, target_section: str, conversation_message_id: int = None):
    prices = {
        "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
        "synastry": 1500, "palmistry": 1200, "all": 3000, "oracle": 500, "antitaro": 500,
        "tariff_1": 990, "tariff_2": 2900, "tariff_vip": 5900
    }
    price_of_service = prices.get(target_section, 0)
    user = await get_user(vk_id)
    if user and price_of_service > 0:
        await update_user(vk_id, {"balance": user.get("balance", 0) + price_of_service})

    msg = "🛑 КАНАЛ СВЯЗИ НЕСТАБИЛЕН\n\nЗвезды скрылись за облаками матрицы. Энергия возвращена на твой баланс. Попробуй инициировать ритуал снова через минуту."

    await stop_dynamic_typing(peer_id)
    await ghost_edit(
        bot.api,
        peer_id,
        msg,
        conversation_message_id=conversation_message_id,
        keyboard=get_main_keyboard(vk_id)
    )
