with open("modules/profile.py", "r") as f:
    content = f.read()
old_code = """    user = await get_user(vk_id)
    if not user:
        await message.answer("Сначала зарегистрируйся в системе (напиши Начать).")
        return"""
new_code = """    user = await get_user(vk_id)
    is_new = False
    if not user:
        from database import create_user
        user = await create_user(vk_id, "", "", "")
        is_new = True"""
content = content.replace(old_code, new_code)
old_finish = """    await message.answer(f"ПЕЧАТЬ АКТИВИРОВАНА! Тебе начислено 500 Энергии звезд. Твой баланс: {user_balance} Энергии звезд")

    try:"""
new_finish = """    await message.answer(f"ПЕЧАТЬ АКТИВИРОВАНА! Тебе начислено 500 Энергии звезд. Твой баланс: {user_balance} Энергии звезд")

    if is_new:
        from modules.registration import start_handler
        await start_handler(message)

    try:"""
content = content.replace(old_finish, new_finish)
with open("modules/profile.py", "w") as f:
    f.write(content)
