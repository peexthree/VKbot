with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

# We need to ensure that the referral link has the correct group ID and uses the "ПЕЧАТЬ" logic,
# because that's how the referral works in this bot (sending "ПЕЧАТЬ-{vk_id}" to the group).

old_ref_logic = """        elif cmd == "get_referral":
            bot_domain = "anti_taro_bot" # Fallback if you don't query it dynamically
            try:
                groups_info = await bot.api.groups.get_by_id()
                if groups_info:
                    bot_domain = groups_info[0].screen_name
            except Exception:
                pass

            ref_link = f"https://vk.com/write-{groups_info[0].id}?ref={vk_id}" if 'groups_info' in locals() and groups_info else f"https://vk.com/im?sel=-219181948&ref={vk_id}"
            await bot.api.messages.send(
                peer_id=peer_id,
                message=f"Твоя персональная ссылка для друзей:\\n{ref_link}\\n\\nКак только друг активирует бота, ты получишь 500 Энергии звезд.",
                random_id=0
            )"""

new_ref_logic = """        elif cmd == "get_referral":
            # Direct link to group 219181948 sending text ПЕЧАТЬ-{vk_id}
            ref_link = f"https://vk.com/im?sel=-219181948&text=ПЕЧАТЬ-{vk_id}"
            await bot.api.messages.send(
                peer_id=peer_id,
                message=f"Твоя персональная ссылка для друзей:\\n{ref_link}\\n\\nОтправь этот код/ссылку новому адепту. Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд.",
                random_id=0
            )"""

content = content.replace(old_ref_logic, new_ref_logic)

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
