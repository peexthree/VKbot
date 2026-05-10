with open("modules/services.py", "r") as f:
    content = f.read()
content = content.replace(
    "from modules.utils import (\n    get_fsm_step,\n    upload_local_photo,\n)",
    "from modules.utils import (\n    get_fsm_step,\n    upload_local_photo,\n    get_storefront_keyboard,\n)"
)
old_fallback = """        fallback_kb = Keyboard(inline=True)
        fallback_kb.add(Callback("🏠 ГЛАВНОЕ МЕНЮ", payload={"cmd": "main_menu"}), color=KeyboardButtonColor.PRIMARY)

        fallback_msg = f"{header_text}\\n\\n(Ошибка отображения витрины. Пожалуйста, вернитесь в главное меню)"
        try:
            if edit_msg_id:
                await bot.api.messages.edit(peer_id=peer_id, message=fallback_msg, conversation_message_id=edit_msg_id, keyboard=fallback_kb.get_json())
            else:
                await bot.api.messages.send(peer_id=peer_id, message=fallback_msg, keyboard=fallback_kb.get_json(), random_id=0)"""
new_fallback = """        fallback_msg = f"{header_text}\\n\\n(Ошибка карусели. Используйте резервное меню)"
        fallback_kb_json = await get_storefront_keyboard({})

        try:
            if edit_msg_id:
                await bot.api.messages.edit(peer_id=peer_id, message=fallback_msg, conversation_message_id=edit_msg_id, keyboard=fallback_kb_json)
            else:
                await bot.api.messages.send(peer_id=peer_id, message=fallback_msg, keyboard=fallback_kb_json, random_id=0)"""
content = content.replace(old_fallback, new_fallback)
with open("modules/services.py", "w") as f:
    f.write(content)
