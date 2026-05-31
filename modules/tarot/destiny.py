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
    """Информация о Карте Судьбы перед покупкой"""
    user = await get_user(vk_id)
    if not user: return

    purchased = user.get("purchased_sections", {})
    if purchased.get("destiny_card_purchased"):
        # Если уже куплена, просто показываем результат (или перенаправляем в гримуар)
        from modules.profile.views import show_profile_logic
        await show_profile_logic(vk_id, peer_id, conversation_message_id=conversation_message_id)
        return

    text = (
        "⭐ ТВОЯ КАРТА СУДЬБЫ (DESTINY CARD) ⭐\n\n"
        "Это не просто ежедневный расклад. Это твой сакральный код, рассчитанный по дате твоего рождения.\n\n"
        "ЧТО ТЫ УЗНАЕШЬ:\n"
        "✅ Твой главный жизненный путь и предназначение.\n"
        "✅ Кармические задачи и уроки души.\n"
        "✅ Твои скрытые сильные и слабые стороны.\n"
        "✅ Рекомендации и аффирмации на всю жизнь.\n\n"
        "Генерируется ОДИН РАЗ и навсегда закрепляется за твоим профилем в Гримуаре.\n\n"
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

async def generate_destiny_card_logic(vk_id: int, peer_id: int, conversation_message_id: int = None):
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
    purchased = user.get("purchased_sections", {})
    purchased["destiny_card_purchased"] = True
    await update_user(vk_id, {
        "balance": balance - 1500,
        "purchased_sections": purchased
    })

    await start_dynamic_typing(bot.api, peer_id, conversation_message_id=conversation_message_id)

    try:
        from cache import get_temp_birth_data
        birth_data = await get_temp_birth_data(vk_id)
        if not birth_data:
            await stop_dynamic_typing(peer_id)
            # Return energy
            purchased = user.get("purchased_sections", {})
            purchased.pop("destiny_card_purchased", None)
            await update_user(vk_id, {"balance": balance + 1500, "purchased_sections": purchased})

            # Переводим на ввод данных
            await set_user_state(vk_id, '{"step": "waiting_birth_date", "target_section": "destiny_card"}')
            await bot.api.messages.send(peer_id=peer_id, message="🛑 Для расчета КАРТЫ СУДЬБЫ мне нужно заново настроиться на твою энергию. Энергия возвращена. Пожалуйста, введи свою ДАТУ рождения (например, 15.04.1990):", random_id=0)
            return

        birth_date = birth_data.get("date", "")
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
            return_json=True
        )

        res_text = res_data.get("text", "") if isinstance(res_data, dict) else res_data

        if not res_text:
            await stop_dynamic_typing(peer_id)
            purchased = user.get("purchased_sections", {})
            purchased.pop("destiny_card_purchased", None)
            await update_user(vk_id, {"balance": balance + 1500, "purchased_sections": purchased})
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
                "date": datetime.datetime.now().strftime("%d.%m.%Y")
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

        await ghost_edit(
            bot.api,
            peer_id,
            header + res_text,
            message_id=typing_msg_id,
            conversation_message_id=conversation_message_id,
            attachment=att,
            keyboard=kb
        )

    except Exception as e:
        logger.error(f"Error generating destiny card: {e}")
        await stop_dynamic_typing(peer_id)
        # Возвращаем энергию в случае ошибки
        purchased = user.get("purchased_sections", {})
        purchased.pop("destiny_card_purchased", None)
        await update_user(vk_id, {"balance": balance + 1500, "purchased_sections": purchased})
        await bot.api.messages.send(peer_id=peer_id, message="🛑 Произошла ошибка при обращении к звездам. Энергия возвращена.", random_id=0)
