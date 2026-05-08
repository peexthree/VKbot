import os

with open("modules/tarot.py", "r", encoding="utf-8") as f:
    content = f.read()

# We need a function to check Grimoire Master unlock.
# "Major Arcana" are cards "0" to "21".
# If they have all 22, we unlock "Магистр" skin and/or a 10% discount logic.
# Or just "Магистр" skin. Wait, the rule says: "Собрал все 22 Старших Аркана — получил уникальный скин «Магистр»".
# This logic should be placed after unlocked_cards is updated.

master_check_code = """
        # Gamification: Check for Master skin
        if user:
            major_arcana = [str(i) for i in range(22)]
            unlocked = user.get("unlocked_cards", {})
            if isinstance(unlocked, dict) and all(arc in unlocked for arc in major_arcana):
                purchased_skins = user.get("purchased_skins", [])
                if "Магистр" not in purchased_skins:
                    purchased_skins.append("Магистр")
                    await update_user(vk_id, {"purchased_skins": purchased_skins})
                    try:
                        await bot.api.messages.send(
                            peer_id=peer_id,
                            message="👁‍🗨 ИНИЦИАЦИЯ ПРОЙДЕНА 👁‍🗨\n\nТы собрал все 22 Старших Аркана в своем Гримуаре. Тебе открыт уникальный аватар-проводник: МАГИСТР.\n\nЗайди в Мой профиль -> Настройки -> Выбрать персонажа.",
                            random_id=0
                        )
                    except Exception:
                        pass
"""

# Inside oracle
old_oracle_update = """            await update_user(vk_id, {"purchased_sections": purchased, "total_cards_received": current_total + 3, "unlocked_cards": unlocked_cards})
        else:
            await update_user(vk_id, {"purchased_sections": purchased})"""

new_oracle_update = """            await update_user(vk_id, {"purchased_sections": purchased, "total_cards_received": current_total + 3, "unlocked_cards": unlocked_cards})
            major_arcana = [str(i) for i in range(22)]
            if all(arc in unlocked_cards for arc in major_arcana):
                purchased_skins = user.get("purchased_skins", [])
                if "Магистр" not in purchased_skins:
                    purchased_skins.append("Магистр")
                    await update_user(vk_id, {"purchased_skins": purchased_skins})
                    try:
                        await bot.api.messages.send(
                            peer_id=vk_id,
                            message="👁‍🗨 ИНИЦИАЦИЯ ПРОЙДЕНА 👁‍🗨\\n\\nТы собрал все 22 Старших Аркана в своем Гримуаре. Тебе открыт уникальный аватар-проводник: МАГИСТР.\\n\\nЗайди в Мой профиль -> Настройки -> Выбрать персонажа.",
                            random_id=0
                        )
                    except Exception:
                        pass
        else:
            await update_user(vk_id, {"purchased_sections": purchased})"""

content = content.replace(old_oracle_update, new_oracle_update)

# Inside card_of_day
old_cod_update = """        if card_id in unlocked_cards and unlocked_cards[card_id] == "Первое касание":
            grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
            signature = await generate_text(grimoire_prompt, skin=active_skin)
            if signature:
                unlocked_cards[card_id] = signature
                await update_user(vk_id, {"unlocked_cards": unlocked_cards})"""

new_cod_update = """        if card_id in unlocked_cards and unlocked_cards[card_id] == "Первое касание":
            grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
            signature = await generate_text(grimoire_prompt, skin=active_skin)
            if signature:
                unlocked_cards[card_id] = signature
                await update_user(vk_id, {"unlocked_cards": unlocked_cards})

        user = await get_user(vk_id)
        if user:
            major_arcana = [str(i) for i in range(22)]
            unlocked = user.get("unlocked_cards", {})
            if isinstance(unlocked, dict) and all(arc in unlocked for arc in major_arcana):
                purchased_skins = user.get("purchased_skins", [])
                if "Магистр" not in purchased_skins:
                    purchased_skins.append("Магистр")
                    await update_user(vk_id, {"purchased_skins": purchased_skins})
                    try:
                        await bot.api.messages.send(
                            peer_id=peer_id,
                            message="👁‍🗨 ИНИЦИАЦИЯ ПРОЙДЕНА 👁‍🗨\\n\\nТы собрал все 22 Старших Аркана в своем Гримуаре. Тебе открыт уникальный аватар-проводник: МАГИСТР.\\n\\nЗайди в Мой профиль -> Настройки -> Выбрать персонажа.",
                            random_id=0
                        )
                    except Exception:
                        pass"""

content = content.replace(old_cod_update, new_cod_update)

with open("modules/tarot.py", "w", encoding="utf-8") as f:
    f.write(content)
