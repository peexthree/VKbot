import asyncio
import datetime
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

            await start_dynamic_typing(bot.api, vk_id)
            try:
                await asyncio.sleep(4)
            finally:
                await stop_dynamic_typing(vk_id)

            from modules.keyboards import get_main_reply_keyboard
            await bot.api.messages.send(
                peer_id=vk_id,
                message=f"✦ ШЕПОТ МАТРИЦЫ ✦\n\n{insight}",
                random_id=0,
                keyboard=get_main_reply_keyboard(vk_id)
            )
            from modules.services import show_services
            await show_services(vk_id, vk_id, 0)
            return

        purchased = user.get("purchased_sections", {})
        if section == "all":
            purchased.update({"sex": True, "money": True, "shadow": True, "final": True, "all": True})
            await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})
            await ghost_edit(bot.api, vk_id, "УСЛУГА АКТИВИРОВАНА. Все Врата открыты.", keyboard=get_main_keyboard(vk_id))
        elif section == "oracle":
            purchased["oracle_access"] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, '{"step": "waiting_oracle_question"}')
            await ghost_edit(bot.api, vk_id, "УСЛУГА АКТИВИРОВАНА. НАПИШИ СВОЙ ВОПРОС СУДЬБЕ.", keyboard=get_main_keyboard(vk_id))
            return
        elif section == "synastry":
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await set_user_state(vk_id, '{"step": "waiting_synastry_name"}')
            await ghost_edit(bot.api, vk_id, "УСЛУГА АКТИВИРОВАНА. НАПИШИ ИМЯ ПАРТНЕРА.", keyboard=get_main_keyboard(vk_id))
            return
        else:
            purchased[section] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            await ghost_edit(bot.api, vk_id, "УСЛУГА АКТИВИРОВАНА.", keyboard=get_main_keyboard(vk_id))

        await set_user_state(vk_id, f'{{"step": "global_cut", "target_section": "{section}"}}')
        kb = Keyboard(inline=True)
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)

        await asyncio.sleep(2)
        await ghost_edit(bot.api, vk_id, "ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже.", keyboard=kb.get_json())
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

        await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)

        try:
            p = user.get("purchased_sections", {})
            active_skin = user.get("active_skin", "olesya")
            tags = user.get("tags", [])

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
                await asyncio.sleep(4)

                display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", res_text).strip()

                history = user.get("readings_history", [])
                if not isinstance(history, list): history = []

                titles = {
                    "sex": "Сексуальность", "money": "Богатство", "shadow": "Тень",
                    "final": "Путь", "synastry": "Синастрия", "oracle": "Оракул",
                    "antitaro": "Антитаро", "report": "Разбор", "card_of_day": "Карта дня"
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

                purchased = user.get("purchased_sections", {})
                if target_section in purchased:
                    purchased[target_section] = False
                    save_data["purchased_sections"] = purchased

                if target_section == "card_of_day":
                    save_data["balance"] = user.get("balance", 0) + 100
                    save_data["visit_streak"] = user.get("visit_streak", 0) + 1
                    purchased["card_of_day_last_used"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    save_data["purchased_sections"] = purchased

                if isinstance(res_data, dict):
                    res_data["text"] = display_text
                    save_data["latest_reading_data"] = res_data
                else:
                    save_data["latest_reading_data"] = {"text": display_text}

                await update_user(vk_id, save_data)

                async def extract_and_save_tags(v_id: int, text: str):
                    new_tags = await extract_tags(text)
                    if new_tags:
                        await update_user(v_id, {"tags": new_tags})

                asyncio.create_task(extract_and_save_tags(vk_id, res_text))

                light_kb = Keyboard(inline=True)
                light_kb.add(Callback("📜 ЗАБРАТЬ ПОЛНЫЙ PDF-ОТЧЕТ", payload={"cmd": "gen_pdf", "section": target_section, "card": card_id}), color=KeyboardButtonColor.POSITIVE)
                light_kb.row()
                light_kb.add(Callback("🏠 В ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
                kb_str = light_kb.get_json()

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

                await stop_dynamic_typing(peer_id)

                header = ""
                if card_data:
                    header = f"🃏 {card_data.get('name')} — {card_data.get('subtitle')}\n------------------\n\n"

                await ghost_edit(
                    bot.api,
                    peer_id,
                    header + display_text,
                    conversation_message_id=conversation_message_id,
                    keyboard=kb_str
                )
            else:
                await handle_generation_failure(vk_id, peer_id, target_section, conversation_message_id=conversation_message_id)
        finally:
            await stop_dynamic_typing(peer_id)
    except Exception as e:
        logger.error(f"Ошибка в execute_generation: {str(e)}")
        await handle_generation_failure(vk_id, peer_id, target_section, conversation_message_id=conversation_message_id)
    finally:
        await stop_dynamic_typing(peer_id)
        await release_lock(lock_key)

async def handle_generation_failure(vk_id: int, peer_id: int, target_section: str, conversation_message_id: int = None):
    prices = {
        "sex": 1000, "money": 900, "shadow": 700, "final": 1200,
        "synastry": 1500, "all": 3000, "oracle": 500, "antitaro": 500,
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
