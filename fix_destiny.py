import re

with open('modules/tarot/destiny.py', 'r') as f:
    content = f.read()

# Fix balance NameError by calculating new_balance appropriately
new_logic = """    try:
        birth_date = user.get("birth_date", "")
        if not birth_date:
            await stop_dynamic_typing(peer_id)
            # Return energy
            purchased = user.get("purchased_sections", {})
            purchased.pop("destiny_card_purchased", None)
            await update_user(vk_id, {"balance": balance + 1500, "purchased_sections": purchased})
            await bot.api.messages.send(peer_id=peer_id, message="🛑 Ошибка: не указана дата рождения. Пожалуйста, заполните профиль в настройках (Энергия возвращена).", random_id=0)
            return

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
            "destiny_card", birth_date, user.get("birth_time", ""),
            user.get("birth_city", ""), user.get("core_profile", ""),
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

        # Сохраняем в историю и спец поле"""

content = re.sub(
    r'    try:\n        birth_date = user.get\("birth_date", ""\).*?        # Сохраняем в историю и спец поле',
    new_logic,
    content,
    flags=re.DOTALL
)

# Also fix the fallback in the outer except block
content = content.replace('await update_user(vk_id, {"balance": balance})', 'purchased = user.get("purchased_sections", {}); purchased.pop("destiny_card_purchased", None); await update_user(vk_id, {"balance": balance + 1500, "purchased_sections": purchased})')

with open('modules/tarot/destiny.py', 'w') as f:
    f.write(content)
