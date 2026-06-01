import datetime
from loguru import logger
from database import get_user, update_user, set_user_state
from modules.bot_init import bot
from modules.utils import (
    upload_local_photo, ghost_edit,
    start_dynamic_typing, stop_dynamic_typing
)
from modules.utils.logic import calculate_destiny_card
from modules.keyboards import after_pdf_kb

async def destiny_card_info_logic(vk_id: int, peer_id: int, conversation_message_id: int = None):
    """Информация о Карте Судьбы или вывод купленной"""
    user = await get_user(vk_id)
    if not user: return

    purchased = user.get("purchased_sections", {})
    destiny_data = user.get("destiny_card_data")

    if purchased.get("destiny_card_purchased") and destiny_data:
        # ВЫВОД КУПЛЕННОЙ КАРТЫ
        from cards_data import get_card_data
        card_id = destiny_data.get("card_id", "0")
        card_data = get_card_data(card_id)
        res_text = destiny_data.get("text", "")

        from modules.keyboards import after_pdf_kb
        # Добавляем кнопку обновления в клавиатуру (через модификацию или новую функцию)
        kb = Keyboard(inline=True)
        kb.add(Callback("📜 ПОЛНЫЙ PDF-ОТЧЕТ", payload={"cmd": "gen_pdf", "section": "destiny_card", "card": card_id}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Callback("🔄 ОБНОВИТЬ (1000 ✨)", payload={"cmd": "confirm_buy", "type": "service", "key": "destiny_card_update"}), color=KeyboardButtonColor.PRIMARY)
        kb.row()
        kb.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)
        kb_json = kb.get_json()

        header = f"⭐ ТВОЯ КАРТА СУДЬБЫ: {card_data.get('name')} ⭐\n------------------\n\n"
        att = await upload_local_photo(bot.api, f"{card_id}.jpeg", peer_id=vk_id)

        await ghost_edit(
            bot.api,
            peer_id,
            header + res_text,
            conversation_message_id=conversation_message_id,
            attachment=att,
            keyboard=kb_json
        )
        return

    # ЭКРАН ПОКУПКИ
    text = (
        "⭐ ТВОЯ КАРТА СУДЬБЫ (DESTINY CARD) ⭐\n\n"
        "Это не просто ежедневный расклад. Это твой сакральный код, рассчитанный по дате твоего рождения.\n\n"
        "ЧТО ТЫ УЗНАЕШЬ:\n"
        "✅ Твой главный жизненный путь и предназначение.\n"
        "✅ Кармические задачи и уроки души.\n"
        "✅ Твои скрытые сильные и слабые стороны.\n"
        "✅ Пожизненные рекомендации и аффирмации.\n"
        "✅ ИНТЕРЕСНЫЕ ФАКТЫ о твоем воплощении.\n\n"
        "Генерируется один раз и доступна в профиле навсегда.\n\n"
        "Стоимость активации: 1500 ✨"
    )

    from modules.keyboards import confirmation_kb
    kb = confirmation_kb({"cmd": "buy_destiny_card"}, 1500)

    att = await upload_local_photo(bot.api, "uslugi/WAYLIFE.jpeg", peer_id=vk_id)

    await ghost_edit(
        bot.api,
        peer_id,
        text,
        conversation_message_id=conversation_message_id,
        attachment=att,
        keyboard=kb
    )

async def generate_destiny_card_logic(vk_id: int, peer_id: int, conversation_message_id: int = None, is_update: bool = False):
    """Генерация Карты Судьбы"""
    user = await get_user(vk_id)
    if not user: return

    balance = int(user.get("balance", 0) or 0)
    if balance < 1500:
        from modules.services import show_tariffs
        await bot.api.messages.send(peer_id=peer_id, message="❌ Недостаточно энергии для активации Карты Судьбы.", random_id=0)
        await show_tariffs(vk_id, peer_id)
        return

    # Списываем энергию
    cost = 1000 if is_update else 1500
    if balance < cost:
        from modules.services import show_tariffs
        await bot.api.messages.send(peer_id=peer_id, message=f"❌ Недостаточно энергии для {'обновления' if is_update else 'активации'} Карты Судьбы.", random_id=0)
        await show_tariffs(vk_id, peer_id)
        return

    purchased = user.get("purchased_sections", {})
    if not is_update:
        purchased["destiny_card_purchased"] = True

    await update_user(vk_id, {
        "balance": balance - cost,
        "purchased_sections": purchased
    })

    await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)

    try:
        from cache import get_temp_birth_data
        birth_data = await get_temp_birth_data(vk_id)
        if not birth_data:
            await stop_dynamic_typing(peer_id)
            # Return energy
            if not is_update:
                purchased.pop("destiny_card_purchased", None)
            await update_user(vk_id, {"balance": balance, "purchased_sections": purchased})

            # Переводим на ввод данных
            await set_user_state(vk_id, json.dumps({"step": "waiting_birth_date", "target_section": "destiny_card_update" if is_update else "destiny_card"}))
            await bot.api.messages.send(peer_id=peer_id, message="🛑 Для расчета КАРТЫ СУДЬБЫ мне нужно заново настроиться на твою энергию. Энергия возвращена. Пожалуйста, введи свою ДАТУ рождения (например, 15.04.1990):", random_id=0)
            return

        birth_date = birth_data.get("date", "")

        # Если это обновление, берем уже существующий ID карты
        if is_update and user.get("destiny_card_data"):
            db_idx = int(user.get("destiny_card_data").get("card_id", 0))
        else:
            card_index = calculate_destiny_card(birth_date)
            # Арканы 1-22 в нашем tarot_db.json соответствуют индексам 1-22 (Шут там 0, но по нашей логике он может быть 22)
            # Если Аркан 22 - это Шут (0), но в db он 0. Сделаем маппинг.
            db_idx = card_index if card_index < 22 else 0

        from cards_data import get_card_data
        card_data = get_card_data(str(db_idx))

        from ai_service import generate_section
        active_skin = user.get("active_skin", "olesya")

        # Специальный промпт для карты судьбы
        res_data = await generate_section(
            "destiny_card", birth_date, birth_data.get("time", ""),
            birth_data.get("city", ""), user.get("core_profile", ""),
            user.get("first_name", "Адепт"), user.get("sex_val", 0),
            skin=active_skin, card_id=str(db_idx), card_data=card_data,
            return_json=True,
            purchased_skins=user.get("purchased_skins", [])
        )

        res_text = res_data.get("text", "") if isinstance(res_data, dict) else res_data

        if not res_text:
            await stop_dynamic_typing(peer_id)
            purchased = user.get("purchased_sections", {})
            if not is_update:
                purchased.pop("destiny_card_purchased", None)
            await update_user(vk_id, {"balance": balance, "purchased_sections": purchased})
            await bot.api.messages.send(peer_id=peer_id, message="🛑 Произошла ошибка при обращении к звездам (пустой ответ). Энергия возвращена.", random_id=0)
            return

        # Сохраняем в историю и спец поле
        history = user.get("readings_history", [])
        history.append({
            "title": "⭐ КАРТА СУДЬБЫ",
            "date": datetime.datetime.now().strftime("%d.%m.%Y"),
            "text": res_text,
            "section": "destiny_card",
            "is_destiny": True
        })

        update_data = {
            "readings_history": history,
            "destiny_card_data": {
                "card_id": str(db_idx),
                "text": res_text,
                "date": datetime.datetime.now().strftime("%d.%m.%Y"),
                "interesting_facts": res_data.get("interesting_facts", "") if isinstance(res_data, dict) else ""
            },
            "latest_reading_text": res_text
        }

        if isinstance(res_data, dict):
            res_data["text"] = res_text
            update_data["latest_reading_data"] = res_data
        else:
            update_data["latest_reading_data"] = {"text": res_text}

        await update_user(vk_id, update_data)

        typing_msg_id = await stop_dynamic_typing(peer_id)

        kb = after_pdf_kb("destiny_card", str(db_idx))

        header = f"⭐ ТВОЯ КАРТА СУДЬБЫ: {card_data.get('name')} ⭐\n------------------\n\n"

        att = await upload_local_photo(bot.api, f"{db_idx}.jpeg", peer_id=vk_id)

        # Кастомная клавиатура с кнопкой ОБНОВИТЬ
        kb_final = Keyboard(inline=True)
        kb_final.add(Callback("📜 ПОЛНЫЙ PDF-ОТЧЕТ", payload={"cmd": "gen_pdf", "section": "destiny_card", "card": str(db_idx)}), color=KeyboardButtonColor.POSITIVE)
        kb_final.row()
        kb_final.add(Callback("🔄 ОБНОВИТЬ (1000 ✨)", payload={"cmd": "confirm_buy", "type": "service", "key": "destiny_card_update"}), color=KeyboardButtonColor.PRIMARY)
        kb_final.row()
        kb_final.add(Callback("🏠 В МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.SECONDARY)

        await ghost_edit(
            bot.api,
            peer_id,
            header + res_text,
            message_id=typing_msg_id,
            conversation_message_id=conversation_message_id,
            attachment=att,
            keyboard=kb_final.get_json()
        )

    except Exception as e:
        logger.error(f"Error generating destiny card: {e}")
        await stop_dynamic_typing(peer_id)
        # Возвращаем энергию в случае ошибки
        purchased = user.get("purchased_sections", {})
        if not is_update:
            purchased.pop("destiny_card_purchased", None)
        await update_user(vk_id, {"balance": balance, "purchased_sections": purchased})
        await bot.api.messages.send(peer_id=peer_id, message="🛑 Произошла ошибка при обращении к звездам. Энергия возвращена.", random_id=0)
