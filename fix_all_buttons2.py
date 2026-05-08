import os

with open("modules/payments.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add a block in message_event_handler to process "profile_action"
handler_logic = """        elif cmd == "profile_action":
            action = payload.get("action")
            if action == "settings":
                from modules.profile import settings_handler
                # Mock a message object
                class MockMsg:
                    def __init__(self, from_id, peer_id):
                        self.from_id = from_id
                        self.peer_id = peer_id
                    async def answer(self, *args, **kwargs):
                        await bot.api.messages.send(peer_id=self.peer_id, random_id=0, *args, **kwargs)
                await settings_handler(MockMsg(vk_id, peer_id))
            elif action == "change_data":
                await set_user_state(vk_id, "waiting_for_onboarding_data")
                kb = Keyboard(inline=True)
                kb.add(Callback("ОТМЕНА", payload={"cmd": "profile_action", "action": "settings"}), color=KeyboardButtonColor.NEGATIVE)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Введите новые данные в формате: ДД.ММ.ГГГГ, Время, Город.", keyboard=kb.get_json())
            elif action == "change_skin":
                from modules.profile import settings_choose_character
                class MockMsg:
                    def __init__(self, from_id, peer_id):
                        self.from_id = from_id
                        self.peer_id = peer_id
                    async def answer(self, *args, **kwargs):
                        await bot.api.messages.send(peer_id=self.peer_id, random_id=0, *args, **kwargs)
                await settings_choose_character(MockMsg(vk_id, peer_id))
            elif action == "cancel_sub":
                await update_user(vk_id, {"transit_sub_expires_at": None})
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Транзит (Подписка) успешно отменен.")
            elif action == "reset_account":
                await set_user_state(vk_id, "waiting_reset_confirm")
                kb = Keyboard(inline=True)
                kb.add(Callback("ПОДТВЕРДИТЬ СБРОС", payload={"cmd": "profile_action", "action": "confirm_reset"}), color=KeyboardButtonColor.NEGATIVE)
                kb.row()
                kb.add(Callback("Назад в профиль", payload={"cmd": "profile_action", "action": "back_to_profile"}), color=KeyboardButtonColor.PRIMARY)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="⚠️ ВНИМАНИЕ: Это действие безвозвратно удалит все ваши данные, покупки и прогресс в системе. Вы уверены?", keyboard=kb.get_json())
            elif action == "confirm_reset":
                from database import delete_user
                await delete_user(vk_id)
                await set_user_state(vk_id, "")
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="СИСТЕМА ОБНУЛЕНА. ТЫ ДЛЯ МЕНЯ ТЕПЕРЬ НИКТО. Напиши 'Начать' для старта с нуля.")
            elif action == "back_to_profile":
                from modules.profile import show_profile
                class MockMsg:
                    def __init__(self, from_id, peer_id):
                        self.from_id = from_id
                        self.peer_id = peer_id
                    async def answer(self, *args, **kwargs):
                        await bot.api.messages.send(peer_id=self.peer_id, random_id=0, *args, **kwargs)
                await show_profile(MockMsg(vk_id, peer_id))
            elif action == "admin_console":
                from modules.admin import show_admin_console
                await show_admin_console(peer_id)
            elif action == "syndicate":
                from modules.profile import syndicate_dashboard_handler
                class MockMsg:
                    def __init__(self, from_id, peer_id):
                        self.from_id = from_id
                        self.peer_id = peer_id
                    async def answer(self, *args, **kwargs):
                        await bot.api.messages.send(peer_id=self.peer_id, random_id=0, *args, **kwargs)
                await syndicate_dashboard_handler(MockMsg(vk_id, peer_id))
            elif action == "grimoire":
                from modules.profile import show_grimoire_page
                await show_grimoire_page(vk_id, peer_id, 0)
            elif action == "tariffs":
                from modules.services import show_tariffs
                await show_tariffs(vk_id, peer_id, 0)
            elif action == "get_seal":
                await set_user_state(vk_id, "")
                text = (
                    "📜 ТВОЯ ПЕЧАТЬ ПРИЗЫВА\\n\\n"
                    f"Код твоей Печати: ПЕЧАТЬ-{vk_id}\\n\\n"
                    "Отправь этот код новому адепту, или скинь ему прямую ссылку: "
                    f"https://vk.com/im?sel=-219181948&text=ПЕЧАТЬ-{vk_id}\\n\\n"
                    "Как только он интегрируется в матрицу, ты получишь 500 Энергии звезд."
                )
                await bot.api.messages.send(peer_id=peer_id, message=text, random_id=0)
            elif action == "enter_seal":
                await set_user_state(vk_id, "waiting_for_seal")
                kb = Keyboard(inline=True)
                kb.add(Callback("Отмена", payload={"cmd": "profile_action", "action": "cancel_seal"}), color=KeyboardButtonColor.NEGATIVE)
                await bot.api.messages.edit(peer_id=peer_id, conversation_message_id=obj.get("conversation_message_id"), message="Введи Печать (код), которую тебе передал Ведущий:", keyboard=kb.get_json())
            elif action == "cancel_seal":
                await set_user_state(vk_id, "")
                from modules.profile import syndicate_dashboard_handler
                class MockMsg:
                    def __init__(self, from_id, peer_id):
                        self.from_id = from_id
                        self.peer_id = peer_id
                    async def answer(self, *args, **kwargs):
                        await bot.api.messages.send(peer_id=self.peer_id, random_id=0, *args, **kwargs)
                await syndicate_dashboard_handler(MockMsg(vk_id, peer_id))"""

content = content.replace('        elif cmd == "buy":', handler_logic + '\n        elif cmd == "buy":')

with open("modules/payments.py", "w", encoding="utf-8") as f:
    f.write(content)
