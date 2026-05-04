import re

with open('modules/payments.py', 'r') as f:
    content = f.read()

# Remove the `@labeler.message(text=...)` decorators for handle_storefront_purchase and process_tariff_purchase
# so they are no longer triggered by text.

content = re.sub(r'@labeler\.message\(text=\[.*?\]\)\nasync def handle_storefront_purchase', 'async def handle_storefront_purchase', content, flags=re.DOTALL)
content = re.sub(r'@labeler\.message\(text=\[.*?\]\)\nasync def process_tariff_purchase', 'async def process_tariff_purchase', content, flags=re.DOTALL)

# Add event handlers to message_event_handler
new_handlers = '''
        if cmd == "service_page":
            try:
                idx = payload.get("idx", 0)
                from modules.services import show_services

                # Try deleting old message entirely
                try:
                    await bot.api.messages.delete(
                        peer_id=peer_id,
                        message_ids=[obj.get("conversation_message_id")],
                        delete_for_all=True
                    )
                except Exception:
                    pass

                await show_services(vk_id, peer_id, idx)
            except Exception as e:
                print(f"Error in service_page: {e}")
            return

        if cmd == "tariff_page":
            try:
                idx = payload.get("idx", 0)
                from modules.services import show_tariffs

                # Try deleting old message entirely
                try:
                    await bot.api.messages.delete(
                        peer_id=peer_id,
                        message_ids=[obj.get("conversation_message_id")],
                        delete_for_all=True
                    )
                except Exception:
                    pass

                await show_tariffs(vk_id, peer_id, idx)
            except Exception as e:
                print(f"Error in tariff_page: {e}")
            return

        if cmd == "buy":
            try:
                buy_type = payload.get("type")
                key = payload.get("key")

                class MockMessage:
                    def __init__(self, from_id, peer_id, text):
                        self.from_id = from_id
                        self.peer_id = peer_id
                        self.text = text

                    async def answer(self, text, **kwargs):
                        try:
                            await bot.api.messages.send(peer_id=self.peer_id, message=text, random_id=0, **kwargs)
                        except Exception:
                            await bot.api.messages.send(peer_id=self.peer_id, message=text, random_id=0)

                # Reverse mapping to text for older functions

                text_mapping = {
                    "sex": "ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ",
                    "money": "КОД ТВОЕГО БОГАТСТВА",
                    "shadow": "ТВОИ СКРЫТЫЕ ГРАНИ",
                    "final": "ТВОЙ ИСТИННЫЙ ПУТЬ",
                    "synastry": "ТАЙНА ВАШИХ ОТНОШЕНИЙ",
                    "all": "ЗОЛОТОЙ АРХИВ ВСЕХ ОТКРОВЕНИЙ",
                    "oracle": "ВОПРОС СУДЬБЕ",
                    "tariff_1": "ТАРИФ 1 (99 РУБ)",
                    "tariff_2": "ТАРИФ 2 (290 РУБ)",
                    "tariff_vip": "VIP БАНДЛ (590 РУБ)"
                }

                mapped_text = text_mapping.get(key, key)
                mock_msg = MockMessage(vk_id, peer_id, mapped_text)

                if buy_type == "service":
                    await handle_storefront_purchase(mock_msg)
                elif buy_type == "tariff":
                    await process_tariff_purchase(mock_msg)
            except Exception as e:
                print(f"Error in buy handler: {e}")
            return
        if cmd == "grimoire_page":'''

match = re.search(r'if cmd == "grimoire_page":', content)
if match:
    content = content[:match.start()] + new_handlers + content[match.end():]
    with open('modules/payments.py', 'w') as f:
        f.write(content)
else:
    print("Could not find grimoire_page")
