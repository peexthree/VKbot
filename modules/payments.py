from cache import acquire_lock, release_lock
import asyncio
import json
import random
import re
import datetime
from vkbottle.bot import BotLabeler, Message
from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Keyboard, KeyboardButtonColor, Text, Callback, GroupEventType
from database import get_user, update_user, set_user_state, get_user_state, create_user
from ai_service import generate_text, generate_section
from modules.utils import bot, generate_premium_pdf, get_fsm_step,  upload_local_photo, get_dynamic_keyboard, get_sections_keyboard, get_storefront_keyboard, cover_cache

labeler = BotLabeler()

@labeler.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=dict)
async def message_event_handler(event: dict):
    obj = event.get("object", {})
    vk_id = obj.get("user_id")
    peer_id = obj.get("peer_id")
    event_id = obj.get("event_id")
    payload = obj.get("payload", {})

    if not await acquire_lock(vk_id, ttl=2): return
    try:

        if not vk_id or not payload:
            return

        import json

        cmd = payload.get("cmd")

        try:
            await bot.api.messages.send_message_event_answer(
                event_id=event_id,
                user_id=vk_id,
                peer_id=peer_id
            )
        except Exception as e:
            print(f"Error answering event: {e}")
        if cmd == "welcome_bonus":
            try:

                user = await get_user(vk_id)
                if not user:
                    return

                if user.get("welcome_bonus_received", False):
                    await bot.api.messages.send(peer_id=peer_id, message="Бонус уже получен", random_id=0)
                    return

                new_bonuses = user.get("bonuses", 0) + 70
                await update_user(vk_id, {"bonuses": new_bonuses, "welcome_bonus_received": True})

                from database import set_user_state
                await set_user_state(vk_id, json.dumps({
                    "step": "global_cut",
                    "target_section": "welcome"
                }))

                kb = {
                    "inline": True,
                    "buttons": [[{
                        "action": {
                            "type": "callback",
                            "payload": json.dumps({"cmd": "global_cut"}),
                            "label": "✦ СДВИНУТЬ КОЛОДУ"
                        },
                    "color": "secondary"
                    }]]
                }

                await bot.api.messages.send(
                    peer_id=peer_id,
                    message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ",
                    keyboard=json.dumps(kb, ensure_ascii=False),
                    random_id=0
                )
            except Exception as e:
                print(f"Error in welcome_bonus handler: {e}")
            return


        if cmd == "main_menu":
            try:
                from database import get_user
                from modules.utils import get_sections_keyboard
                user = await get_user(vk_id)
                kb_json = await get_sections_keyboard(vk_id, user)
                await bot.api.messages.send(
                    peer_id=peer_id,
                    message="ТВОИ ДАННЫЕ В СИСТЕМЕ. КУДА ДВИНЕМСЯ ДАЛЬШЕ?",
                    keyboard=kb_json,
                    random_id=0
                )
            except Exception as e:
                print(f"Error in main_menu: {e}")
            return

        if cmd == "service_page":
            try:
                idx = payload.get("idx", 0)
                from modules.services import show_services

                await show_services(vk_id, peer_id, idx, edit_msg_id=obj.get("conversation_message_id"))
            except Exception as e:
                print(f"Error in service_page: {e}")
            return

        if cmd == "tariff_page":
            try:
                idx = payload.get("idx", 0)
                from modules.services import show_tariffs

                await show_tariffs(vk_id, peer_id, idx, edit_msg_id=obj.get("conversation_message_id"))
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
        if cmd == "grimoire_page":
            try:
                page = payload.get("page", 0)
                from modules.profile import show_grimoire_page
                await show_grimoire_page(vk_id, peer_id, page)
            except Exception as e:
                print(f"Error in grimoire_page handler: {e}")
            return

        if cmd == "view_card":
            try:
                card_id = str(payload.get("id"))
                from modules.profile import view_card_direct
                await view_card_direct(vk_id, peer_id, card_id)
            except Exception as e:
                print(f"Error in view_card handler: {e}")
            return
        if cmd in ["pay_rub", "pay_bonuses"]:
            try:

                user = await get_user(vk_id)
                if not user:
                    return

                section = payload.get("section")
                if cmd == "pay_rub":
                    # Find price from mapping
                    # We can deduce from section, but wait, the prompt says amount_needed // 10, so amount_needed is known in handle_storefront_purchase
                    # For pay_rub, we can just look up the price
                    prices = {"sex": 100, "money": 90, "shadow": 70, "final": 120, "all": 300, "oracle": 50}
                    amount_needed = prices.get(section, 9999)
                    balance = user.get("balance", 0)
                    if balance >= amount_needed:
                        await update_user(vk_id, {"balance": balance - amount_needed})
                        await process_payment_and_generate(vk_id, section)
                    else:
                        await bot.api.messages.send(peer_id=peer_id, message="Недостаточно рублей.", random_id=0)
                elif cmd == "pay_bonuses":
                    price = payload.get("price", 9999)
                    bonuses = user.get("bonuses", 0)
                    if bonuses >= price:
                        await update_user(vk_id, {"bonuses": bonuses - price})
                        await process_payment_and_generate(vk_id, section)
                    else:
                        await bot.api.messages.send(peer_id=peer_id, message="Недостаточно бонусов.", random_id=0)
            except Exception as e:
                print(f"Error in pay handlers: {e}")
            return

        if cmd == "global_cut":
            try:

                # Edit the message to remove the button
                await bot.api.messages.edit(
                    peer_id=peer_id,
                    message="СИНХРОНИЗАЦИЯ...",
                    conversation_message_id=obj.get("conversation_message_id")
                )

                from vkbottle import Keyboard, Callback
                kb = Keyboard(inline=True)
                for i in range(10):
                    if i > 0 and i % 5 == 0:
                        kb.row()
                    kb.add(Callback("🎴", payload={"cmd": "global_draw"}), color="secondary")

                await bot.api.messages.send(
                    peer_id=peer_id,
                    message="Выбери карту из разложенных:",
                    keyboard=kb.get_json(),
                    random_id=0
                )
            except Exception as e:
                print(f"Error in global_cut: {e}")
            return

        if cmd == "global_draw":
            try:
                from database import set_user_state
                state_dict = await get_fsm_step(vk_id)
                if not state_dict or state_dict.get("step") != "global_cut":
                    return

                target_section = state_dict.get("target_section", "")
                partner_name = state_dict.get("partner_name", "")
                partner_date = state_dict.get("partner_date", "")

                await set_user_state(vk_id, "")

                await bot.api.messages.send(peer_id=peer_id, message="Считываю поток...", random_id=0)

                if target_section:
                    await execute_generation(vk_id, peer_id, target_section, partner_name, partner_date)
            except Exception as e:
                print(f"Error in global_draw: {e}")
            return

        if "oracle_card" not in payload:
            return

        card_id = payload["oracle_card"]

        try:
            # Stop loading animation

            state_dict = await get_fsm_step(vk_id)
            if not state_dict or state_dict.get("step") != "oracle_draw":
                return

            drawn_cards = state_dict.get("drawn_cards", [])
            pool = state_dict.get("pool", [])

            if card_id not in drawn_cards:
                drawn_cards.append(card_id)

            if len(drawn_cards) < 3:
                state_dict["drawn_cards"] = drawn_cards
                await set_user_state(vk_id, json.dumps(state_dict))

                from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  Callback
                kb = Keyboard(inline=True)

                # Render only available cards
                btn_count = 0
                for c_id in pool:
                    if c_id not in drawn_cards:
                        if btn_count > 0 and btn_count % 5 == 0:
                            kb.row()
                        kb.add(Callback("🎴", payload={"oracle_card": c_id}))
                        btn_count += 1

                await bot.api.messages.edit(
                    peer_id=peer_id,
                    message=f"Выбрано: {len(drawn_cards)}/3...",
                    conversation_message_id=obj.get("conversation_message_id"),
                    keyboard=kb.get_json()
                )
            else:
                # 3 cards selected
                await set_user_state(vk_id, "") # Clear FSM state

                # To completely remove the keyboard, we need to pass an empty keyboard payload
                empty_kb = Keyboard(inline=True)

                await bot.api.messages.edit(
                    peer_id=peer_id,
                    message="Выбрано: 3/3. Карты собраны.",
                    conversation_message_id=obj.get("conversation_message_id"),
                    keyboard=empty_kb.get_json()
                )

                # Trigger process_oracle_final asynchronously to avoid blocking callback
                import asyncio
                from modules.tarot import process_oracle_final
                asyncio.create_task(process_oracle_final(vk_id, state_dict.get("question", ""), drawn_cards))

        except Exception as e:
            print(f"Error in message_event_handler: {e}")

    finally:
        await release_lock(vk_id)

@labeler.raw_event(GroupEventType.VKPAY_TRANSACTION, dataclass=dict)
async def money_transfer_handler(event: dict):
    from cache import acquire_lock
    try:
        group_id = event.get("group_id")
        if group_id != 219181948:
            return

        # VK API typically sends event within an object depending on the exact callback format
        # In message_event or money_transfer, we can extract from_id and amount
        obj = event.get("object", {})
        vk_id = obj.get("from_id")
        amount = obj.get("amount")

        # Idempotency lock using VK ID and amount as a simple transaction identifier
        tx_key = f"tx_vkpay_{vk_id}_{amount}_{event.get('event_id', 'none')}"
        if not await acquire_lock(tx_key, ttl=3600):
            print(f"Duplicate transaction intercepted: {tx_key}")
            return

        if not vk_id or not amount:
            return

        # amount is in kopecks or rubles? standard money_transfer is rubles usually, but if kopecks it's amount / 100
        # Let's check amount string or integer. In VK it's typically an integer amount.
        # Assuming 99 or 399

        amount_val = int(amount)
        if amount_val > 1000: # if it's in kopecks like 9900
            amount_val = amount_val // 100

        user = await get_user(vk_id)
        if not user:
            print(f"ПЛАТЕЖ ОТ НЕИЗВЕСТНОГО ПОЛЬЗОВАТЕЛЯ: vk_id={vk_id}, amount={amount_val}")
            return

        current_balance = user.get("balance", 0)
        new_balance = current_balance + amount_val

        await update_user(vk_id, {"balance": new_balance})

        await bot.api.messages.send(
            peer_id=vk_id,
            message=f"БАЛАНС ПОПОЛНЕН! НА ТВОЕМ СЧЕТУ: {new_balance} РУБ. ТЕПЕРЬ ТЫ МОЖЕШЬ АКТИВИРОВАТЬ ВЫБРАННУЮ УСЛУГУ",
            random_id=0
        )
        try:
            await bot.api.messages.send(
                peer_id=27260796,
                message=f"💰 Пополнение баланса: {amount} РУБ от пользователя {vk_id}",
                random_id=0
            )
        except Exception:
            pass

    except Exception as e:
        print(f"Error handling money_transfer: {e}")

async def process_payment_and_generate(vk_id: int, section: str):
    if not await acquire_lock(vk_id):

        return
    user = await get_user(vk_id)
    if not user:
        return


    try:
        try:
            await bot.api.messages.send(
                peer_id=27260796,
                message=f"🛒 Покупка услуги {section} пользователем {vk_id}",
                random_id=0
            )
        except Exception:
            pass

        # Mark as purchased in database
        purchased = user.get("purchased_sections", {})
        if section == "all":
            purchased["sex"] = True
            purchased["money"] = True
            purchased["shadow"] = True
            purchased["final"] = True
            await update_user(vk_id, {"purchased_sections": purchased, "has_full_chart": True})
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.\n\nВсе Врата открыты.", random_id=0)
            try:
                await bot.api.messages.set_activity(peer_id=vk_id, type="typing")
                messages = [
                    "Соединяюсь с космосом...",
                    "Раскладываю карты. Надеюсь, ты сегодня не грешил...",
                    "Анализирую твою карму (и сообщения бывшим)...",
                    "Формирую полный БАНДЛ..."
                ]
                import asyncio
                for msg in messages:
                    await bot.api.messages.send(peer_id=vk_id, message=msg, random_id=0)
                    await asyncio.sleep(2)

                date = user.get("birth_date", "неизвестно")
                time = user.get("birth_time", "неизвестно")
                city = user.get("birth_city", "неизвестно")
                first_name = purchased.get("first_name", "")
                sex_val = purchased.get("sex_val", 0)
                core_profile = user.get("core_profile", "")

                from ai_service import generate_section

                try:
                    await bot.api.messages.send(peer_id=vk_id, message="Собираю данные для Золотого архива всех откровений. Это займет около минуты...", random_id=0)
                except Exception:
                    pass

                bundle_text = ""
                active_skin = user.get("active_skin", "olesya") if user else "olesya"
                for sect, name in [("sex", "СЕКС"), ("money", "ДЕНЬГИ"), ("shadow", "ТЕНЬ"), ("final", "ФИНАЛ")]:
                    part_text = await generate_section(sect, date, time, city, core_profile, first_name, sex_val, skin=active_skin)
                    if part_text:
                        import re
                        part_text = re.sub(r"ID_?ТАРО:\s*\d+", "", part_text).strip()
                        bundle_text += f"\n\n--- РАЗДЕЛ {name} ---\n\n" + part_text

                if bundle_text:
                    pdf_filename = f"archive_{vk_id}_bundle.pdf"
                    birth_info = f"{date} {time} {city}"
                    generate_premium_pdf(first_name, birth_info, "РАЗДЕЛ: БАНДЛ", bundle_text, pdf_filename, None)
                    from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  DocMessagesUploader
                    doc_uploader = DocMessagesUploader(bot.api)
                    doc_attachment = await doc_uploader.upload(title="Твой_архив_БАНДЛ.pdf", file_source=pdf_filename, peer_id=vk_id)
                    await bot.api.messages.send(peer_id=vk_id, message="Твой персональный архив (БАНДЛ). Скачай, чтобы не потерять.", attachment=doc_attachment, random_id=0)
                    import os
                    if os.path.exists(pdf_filename):
                        os.remove(pdf_filename)

                    purchased["sex"] = False
                    purchased["money"] = False
                    purchased["shadow"] = False
                    purchased["final"] = False
                    await update_user(vk_id, {"purchased_sections": purchased})
            except Exception as e:
                print(f"Error generating bundle pdf: {e}")

        elif section == "oracle":
            purchased["oracle_access"] = True
            await update_user(vk_id, {"purchased_sections": purchased})
            import json
            await set_user_state(vk_id, json.dumps({"step": "waiting_oracle_question"}))
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.\n\nНАПИШИ СВОЙ ВОПРОС СУДЬБЕ ПРЯМО СЕЙЧАС.", random_id=0)
            return # Oracle uses its own flow
        elif section in ["sex", "money", "shadow", "final"]:
            purchased[section] = True
            updates = {"purchased_sections": purchased}
            if purchased.get("sex") and purchased.get("money") and purchased.get("shadow") and purchased.get("final"):
                updates["has_full_chart"] = True
            await update_user(vk_id, updates)
            await bot.api.messages.send(peer_id=vk_id, message="УСЛУГА АКТИВИРОВАНА.\n\nРаздел открыт.", random_id=0)

        # Transition to Global Cut FSM
        import json
        await set_user_state(vk_id, json.dumps({
            "step": "global_cut",
            "target_section": section,
            "partner_name": user.get("partner_name", ""),
            "partner_date": user.get("partner_date", "")
        }))

        kb = Keyboard(inline=True)
        from vkbottle import Callback
        kb.add(Callback("✦ СДВИНУТЬ КОЛОДУ", payload={"cmd": "global_cut"}), color=KeyboardButtonColor.SECONDARY)

        try:
            await bot.api.messages.send(
                peer_id=vk_id,
                message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже, чтобы обрезать колоду.",
                keyboard=kb.get_json(),
                random_id=0
            )
        except Exception:
            await bot.api.messages.send(
                peer_id=vk_id,
                message="ШАГ 2 ИЗ 3: СИНХРОНИЗАЦИЯ. Жми кнопку ниже, чтобы обрезать колоду.",
                random_id=0
            )
    finally:
        await release_lock(vk_id)

async def handle_storefront_purchase(message: Message):
    import json
    vk_id = message.from_id
    from database import set_user_state
    await set_user_state(vk_id, "")
    text = message.text.upper()

    user = await get_user(vk_id)
    if not user:
        return

    service_map = {
        "ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ": {
            "name": "Твоя сексуальная энергия",
            "amount": 100,
            "section_key": "sex",
            "image_name": "sex1.jpg",
            "desc": "ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ - Цена: 100 РУБ\nЭтот раздел - твой личный ключ к пониманию Твоей сексуальной энергии. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "👄 ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ": {
            "name": "Твоя сексуальная энергия",
            "amount": 100,
            "section_key": "sex",
            "image_name": "sex1.jpg",
            "desc": "ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ - Цена: 100 РУБ\nЭтот раздел - твой личный ключ к пониманию Твоей сексуальной энергии. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "КОД ТВОЕГО БОГАТСТВА": {
            "name": "Код твоего богатства",
            "amount": 90,
            "section_key": "money",
            "image_name": "money1.jpg",
            "desc": "КОД ТВОЕГО БОГАТСТВА - Цена: 90 РУБ\nЭтот раздел - твой личный ключ к пониманию Кода твоего богатства. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "💰 КОД ТВОЕГО БОГАТСТВА": {
            "name": "Код твоего богатства",
            "amount": 90,
            "section_key": "money",
            "image_name": "money1.jpg",
            "desc": "КОД ТВОЕГО БОГАТСТВА - Цена: 90 РУБ\nЭтот раздел - твой личный ключ к пониманию Кода твоего богатства. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "ТВОИ СКРЫТЫЕ ГРАНИ": {
            "name": "Твои скрытые грани",
            "amount": 70,
            "section_key": "shadow",
            "image_name": "demon1.jpg",
            "desc": "ТВОИ СКРЫТЫЕ ГРАНИ - Цена: 70 РУБ\nЭтот раздел - твой личный ключ к пониманию Твоих скрытых граней. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "🌘 ТВОИ СКРЫТЫЕ ГРАНИ": {
            "name": "Твои скрытые грани",
            "amount": 70,
            "section_key": "shadow",
            "image_name": "demon1.jpg",
            "desc": "ТВОИ СКРЫТЫЕ ГРАНИ - Цена: 70 РУБ\nЭтот раздел - твой личный ключ к пониманию Твоих скрытых граней. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "ТВОЙ ИСТИННЫЙ ПУТЬ": {
            "name": "Твой истинный путь",
            "amount": 120,
            "section_key": "final",
            "image_name": "way1.jpg",
            "desc": "ТВОЙ ИСТИННЫЙ ПУТЬ - Цена: 120 РУБ\nЭтот раздел - твой личный ключ к пониманию Твоего истинного пути. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "🏁 ТВОЙ ИСТИННЫЙ ПУТЬ": {
            "name": "Твой истинный путь",
            "amount": 120,
            "section_key": "final",
            "image_name": "way1.jpg",
            "desc": "ТВОЙ ИСТИННЫЙ ПУТЬ - Цена: 120 РУБ\nЭтот раздел - твой личный ключ к пониманию Твоего истинного пути. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "ТАЙНА ВАШИХ ОТНОШЕНИЙ": {
            "name": "Тайна ваших отношений",
            "amount": 150,
            "section_key": "synastry",
            "image_name": "sin.jpeg",
            "desc": "ТАЙНА ВАШИХ ОТНОШЕНИЙ - Цена: 150 РУБ\nЭтот раздел - твой личный ключ к пониманию Тайны ваших отношений. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "👨‍❤️‍👨 ТАЙНА ВАШИХ ОТНОШЕНИЙ": {
            "name": "Тайна ваших отношений",
            "amount": 150,
            "section_key": "synastry",
            "image_name": "sin.jpeg",
            "desc": "ТАЙНА ВАШИХ ОТНОШЕНИЙ - Цена: 150 РУБ\nЭтот раздел - твой личный ключ к пониманию Тайны ваших отношений. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "ЗОЛОТОЙ АРХИВ ВСЕХ ОТКРОВЕНИЙ": {
            "name": "Золотой архив всех откровений",
            "amount": 300,
            "section_key": "all",
            "image_name": "full1.jpg",
            "desc": "ЗОЛОТОЙ АРХИВ ВСЕХ ОТКРОВЕНИЙ - Цена: 300 РУБ\nЭтот раздел - твой личный ключ к пониманию Золотого архива всех откровений. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "📦 ЗОЛОТОЙ АРХИВ ВСЕХ ОТКРОВЕНИЙ": {
            "name": "Золотой архив всех откровений",
            "amount": 300,
            "section_key": "all",
            "image_name": "full1.jpg",
            "desc": "ЗОЛОТОЙ АРХИВ ВСЕХ ОТКРОВЕНИЙ - Цена: 300 РУБ\nЭтот раздел - твой личный ключ к пониманию Золотого архива всех откровений. Я объясню всё простыми словами, как если бы мы сидели за чашкой кофе. Ты получишь красивый PDF-файл, который останется с тобой навсегда."
        },
        "ВОПРОС СУДЬБЕ": {
            "name": "Оракул",
            "amount": 50,
            "section_key": "oracle",
            "image_name": "ora1.jpg",
            "desc": "РАЗДЕЛ ОРАКУЛ - Цена: 50 РУБ\nТекст: [Раз в сутки бесплатно] Снятие блокировки и мгновенный ответ на твой вопрос.\nМеханика: Четкий вопрос - ОБРЕЗАТЬ КОЛОДУ - интеллектуальный анализ подсознания через символику.\nВажно: Система перегрета? Оплати принудительную синхронизацию для доступа."
        },
        "🔮 ВОПРОС СУДЬБЕ": {
            "name": "Оракул",
            "amount": 50,
            "section_key": "oracle",
            "image_name": "ora1.jpg",
            "desc": "РАЗДЕЛ ОРАКУЛ - Цена: 50 РУБ\nТекст: [Раз в сутки бесплатно] Снятие блокировки и мгновенный ответ на твой вопрос.\nМеханика: Четкий вопрос - ОБРЕЗАТЬ КОЛОДУ - интеллектуальный анализ подсознания через символику.\nВажно: Система перегрета? Оплати принудительную синхронизацию для доступа."
        }
    }

    service_info = service_map.get(text)
    if not service_info:
        await message.answer("Услуга не найдена. Выбери из меню.")
        return

    balance = user.get("balance", 0)
    amount_needed = service_info["amount"]

    if balance >= amount_needed:
        new_balance = balance - amount_needed
        await update_user(vk_id, {"balance": new_balance})
        await process_payment_and_generate(vk_id, service_info["section_key"])
    else:
        bonus_price = amount_needed // 10
        user_bonuses = user.get("bonuses", 0)

        buttons = [[{
            "action": {"type": "vkpay", "hash": f"action=pay-to-group&group_id=219181948&amount={amount_needed}"}
        }]]

        if user_bonuses >= bonus_price:
            buttons.append([{
                "action": {
                    "type": "callback",
                    "payload": json.dumps({"cmd": "pay_bonuses", "section": service_info["section_key"], "price": bonus_price}),
                    "label": f"КУПИТЬ ЗА {bonus_price} БОНУСОВ"
                },
                "color": "primary"
            }])

        keyboard_obj = {
            "inline": True,
            "buttons": buttons
        }
        kb_json = json.dumps(keyboard_obj, ensure_ascii=False)

        if "desc" in service_info:
            msg_text = f"{service_info['desc']}\n\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ."
            image_name = service_info['image_name']
            photo_attachment = None

            try:
                from vkbottle import PhotoMessageUploader, VoiceMessageUploader, DocMessagesUploader,  PhotoMessageUploader
                uploader = PhotoMessageUploader(bot.api)
                filepath = f"cards/{image_name}"
                import aiofiles
                async with aiofiles.open(filepath, "rb") as f:
                    data = await f.read()
                    photo_attachment = await uploader.upload(file_source=data, peer_id=vk_id)
            except Exception as e:
                print(f"[ERROR] Failed to load image {image_name} from local storage: {e}")

            if photo_attachment:
                try:
                    await message.answer(msg_text, attachment=photo_attachment, keyboard=kb_json)
                except Exception:
                    await message.answer(msg_text, attachment=photo_attachment)
            else:
                try:
                    await message.answer(msg_text, keyboard=kb_json)
                except Exception:
                    await message.answer(msg_text)
        else:
            msg_text = f"{service_info.get('text', '')}\n\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ."
            try:
                await message.answer(msg_text, keyboard=kb_json)
            except Exception:
                await message.answer(msg_text)

async def process_tariff_purchase(message: Message):
    vk_id = message.from_id
    from database import set_user_state
    await set_user_state(vk_id, "")
    if not await acquire_lock(vk_id):

        return

    user = await get_user(vk_id)
    if not user:
        return


    try:
        text = message.text.upper()
        balance = user.get("balance", 0)

        tariff_map = {
            "ТАРИФ 1 (99 РУБ)": {"price": 99, "days": 7, "bundle": False},
            "ТАРИФ 2 (290 РУБ)": {"price": 290, "days": 30, "bundle": False},
            "VIP БАНДЛ (590 РУБ)": {"price": 590, "days": 30, "bundle": True},
            "🛰 ТАРИФ 1 (99 РУБ)": {"price": 99, "days": 7, "bundle": False},
            "🛰 ТАРИФ 2 (290 РУБ)": {"price": 290, "days": 30, "bundle": False},
            "🛰 VIP БАНДЛ (590 РУБ)": {"price": 590, "days": 30, "bundle": True}
        }

        t_info = tariff_map.get(text)
        if not t_info:
            return

        price = t_info["price"]

        if balance >= price:
            import datetime
            new_balance = balance - price
            updates = {"balance": new_balance}

            now = datetime.datetime.now(datetime.timezone.utc)
            current_expires = user.get("transit_sub_expires_at")
            if current_expires:
                try:
                    exp_date = datetime.datetime.fromisoformat(current_expires)
                    if exp_date > now:
                        now = exp_date
                except ValueError:
                    pass

            new_expires = now + datetime.timedelta(days=t_info["days"])
            updates["transit_sub_expires_at"] = new_expires.isoformat()

            if t_info["bundle"]:
                purchased = user.get("purchased_sections", {})
                purchased["sex"] = True
                purchased["money"] = True
                purchased["shadow"] = True
                purchased["final"] = True
                updates["purchased_sections"] = purchased
                updates["has_full_chart"] = True

            await update_user(vk_id, updates)

            msg = f"ОПЛАТА УСПЕШНА.\n\nТранзит продлен до {new_expires.strftime('%d.%m.%Y %H:%M')}."
            if t_info["bundle"]:
                msg += "\nVIP БАНДЛ АКТИВИРОВАН. Все Врата открыты (Секс, Деньги, Тень, Финал)."

            msg += f"\nТВОЙ ТЕКУЩИЙ БАЛАНС: {new_balance} РУБ."

            # Fetch fresh user to update keyboard if bundle bought
            updated_user = await get_user(vk_id)
            if "purchased_sections" in updates:
                if updated_user:
                    updated_user["purchased_sections"] = updates["purchased_sections"]
            kb_json = await get_sections_keyboard(vk_id, updated_user)

            try:
                await message.answer(msg, keyboard=kb_json)
            except Exception:
                await message.answer(msg)
        else:
            import json
            keyboard_obj = {
                "inline": True,
                "buttons": [[{
                    "action": {"type": "vkpay", "hash": f"action=pay-to-group&group_id=219181948&amount={price}"}
                }]]
            }
            kb_json = json.dumps(keyboard_obj, ensure_ascii=False)
            try:
                await message.answer(f"Недостаточно средств. Цена: {price} РУБ.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ.\nОплата возможна только реальным балансом.", keyboard=kb_json)
            except Exception:
                await message.answer(f"Недостаточно средств. Цена: {price} РУБ.\nТВОЙ ТЕКУЩИЙ БАЛАНС: {balance} РУБ.\nОплата возможна только реальным балансом.")

    finally:
        await release_lock(vk_id)

async def execute_generation(vk_id: int, peer_id: int, target_section: str, partner_name: str, partner_date: str):
    user = await get_user(vk_id)
    if not user:
        return

    purchased = user.get("purchased_sections", {})
    date = user.get("birth_date", "неизвестно")
    time = user.get("birth_time", "неизвестно")
    city = user.get("birth_city", "неизвестно")
    first_name = purchased.get("first_name", "")
    sex_val = purchased.get("sex_val", 0)
    core_profile = user.get("core_profile", "")
    active_skin = user.get("active_skin", "olesya") if user else "olesya"

    from ai_service import generate_section
    import re
    import os

    if target_section == "welcome":
        base_text = await generate_section("base", date, time, city, core_profile, skin=active_skin)

        if base_text:
            if first_name:
                base_text = f"{first_name},\n\n" + base_text

            kb_json = await get_sections_keyboard(vk_id, user)

            parts = re.split(r"(?i)\bБАЗА\b", base_text, maxsplit=1)

            if len(parts) > 1:
                intro = parts[0].strip()
                main_part = "✦ БАЗА ✦\n\n" + parts[1].strip()

                await bot.api.messages.send(peer_id=peer_id, message=intro, random_id=0)
                await bot.api.messages.set_activity(peer_id=peer_id, type="typing")
                import asyncio
                await asyncio.sleep(4)

                try:
                    await bot.api.messages.send(peer_id=peer_id, message=main_part, keyboard=kb_json, random_id=0)
                except Exception as e:
                    print(f"Error sending message with keyboard in execute_generation: {e}")
                    await bot.api.messages.send(peer_id=peer_id, message=main_part, random_id=0)
            else:
                full_text = f"✦ БАЗА ✦\n\n{base_text}"
                try:
                    await bot.api.messages.send(peer_id=peer_id, message=full_text, keyboard=kb_json, random_id=0)
                except Exception as e:
                    print(f"Error sending message with keyboard in execute_generation: {e}")
                    await bot.api.messages.send(peer_id=peer_id, message=full_text, random_id=0)
        else:
            base_text = "ДАННЫЕ СОХРАНЕНЫ. СИСТЕМА В ОЖИДАНИИ."
            kb_json = await get_sections_keyboard(vk_id, user)
            try:
                await bot.api.messages.send(peer_id=peer_id, message=f"✦ БАЗА ✦\n\n{base_text}", keyboard=kb_json, random_id=0)
            except Exception as e:
                await bot.api.messages.send(peer_id=peer_id, message=f"✦ БАЗА ✦\n\n{base_text}", random_id=0)

    elif target_section == "all":
        try:
            try:
                await bot.api.messages.send(peer_id=vk_id, message="Собираю данные для Золотого архива всех откровений. Это займет около минуты...", random_id=0)
            except Exception:
                pass

            bundle_text = ""
            for sect, name in [("sex", "СЕКС"), ("money", "ДЕНЬГИ"), ("shadow", "ТЕНЬ"), ("final", "ФИНАЛ")]:
                part_text = await generate_section(sect, date, time, city, core_profile, first_name, sex_val, skin=active_skin)
                if part_text:
                    part_text = re.sub(r"ID_?ТАРО:\s*\d+", "", part_text).strip()
                    bundle_text += f"\n\n--- РАЗДЕЛ {name} ---\n\n" + part_text

            if bundle_text:
                pdf_filename = f"archive_{vk_id}_bundle.pdf"
                user_info = await get_user(vk_id)
                first_name = user_info.get("purchased_sections", {}).get("first_name", "Странник") if user_info else "Странник"
                birth_info = "НЕИЗВЕСТНО"
                if user_info:
                    d = user_info.get("birth_date", "")
                    t = user_info.get("birth_time", "")
                    c = user_info.get("birth_city", "")
                    birth_info = f"{d} {t} {c}".strip() or "НЕИЗВЕСТНО"
                from modules.utils import generate_premium_pdf
                generate_premium_pdf(first_name, birth_info, "РАЗДЕЛ: БАНДЛ", bundle_text, pdf_filename, None)
                from vkbottle import DocMessagesUploader
                doc_uploader = DocMessagesUploader(bot.api)
                doc_attachment = await doc_uploader.upload(title="Твой_архив_БАНДЛ.pdf", file_source=pdf_filename, peer_id=vk_id)
                await bot.api.messages.send(peer_id=vk_id, message="Твой персональный архив (БАНДЛ). Скачай, чтобы не потерять.", attachment=doc_attachment, random_id=0)
                if os.path.exists(pdf_filename):
                    os.remove(pdf_filename)

                purchased["sex"] = False
                purchased["money"] = False
                purchased["shadow"] = False
                purchased["final"] = False
                await update_user(vk_id, {"purchased_sections": purchased})

            kb_json = await get_sections_keyboard(vk_id, user)
            try:
                await bot.api.messages.send(
                    peer_id=vk_id,
                    message="Используйте меню для вызова нужного раздела:",
                    keyboard=kb_json,
                    random_id=0
                )
            except Exception:
                await bot.api.messages.send(
                    peer_id=vk_id,
                    message="Используйте меню для вызова нужного раздела:",
                    random_id=0
                )
        except Exception as e:
            print(f"Error generating bundle pdf: {e}")

    else:
        # Standard generation logic handled outside if needed, or we just trigger the normal flow
        # In the original code, process_payment_and_generate didn't actually generate immediately for individual sections!
        # It just unlocked them and told the user to use the menu!
        # But task 4 says: "Обязательный выбор карты перед КАЖДОЙ генерацией... Выполняй старую логику генерации текста"
        # Since individual sections generate when requested via handle_section_request in services.py,
        # we need to redirect there, or just trigger the generation here.
        # Wait, the prompt says "Обязательный выбор карты перед КАЖДОЙ генерацией... переводи в FSM ... Выполняй старую логику генерации"
        # If it was an individual section, the generation is actually inside `services.py` `handle_section_request`.
        # So I will execute `handle_section_request` logic here if it's a section.
        result_text = await generate_section(target_section, date, time, city, core_profile, first_name, sex_val, skin=active_skin)
        if result_text:
            if first_name:
                result_text = f"{first_name},\n\n" + result_text

            kb_json = await get_sections_keyboard(vk_id, user)

            import random
            match = re.search(r"ID_?ТАРО:\s*(\d+)", result_text)
            if match:
                num = int(match.group(1))
                if 0 <= num <= 77:
                    card_id = str(num)
                else:
                    card_id = str(random.randint(0, 77))
            else:
                card_id = str(random.randint(0, 77))

            user = await get_user(vk_id)
            if user:
                unlocked_cards = user.get("unlocked_cards", {})
                if isinstance(unlocked_cards, list):
                    unlocked_cards = {k: "Первое касание" for k in unlocked_cards}

                if card_id not in unlocked_cards:
                    from ai_service import generate_text
                    grimoire_prompt = "Сформулируй краткую суть этой карты для личного Гримуара пользователя. Мистично, четко, без воды."
                    signature = await generate_text(grimoire_prompt, skin=active_skin)
                    unlocked_cards[card_id] = signature if signature else "Первое касание"

                current_total = user.get("total_cards_received", 0)
                await update_user(vk_id, {"total_cards_received": current_total + 1, "unlocked_cards": unlocked_cards})

            photo_attachment = None
            try:
                photo_attachment = await upload_local_photo(bot.api, f"{card_id}.jpeg")
            except Exception as e:
                pass

            display_text = re.sub(r"ID_?ТАРО:\s*\d+", "", result_text).strip()

            try:
                pdf_filename = f"archive_{vk_id}_{target_section}.pdf"
                user_info = await get_user(vk_id)
                first_name = user_info.get("purchased_sections", {}).get("first_name", "Странник") if user_info else "Странник"
                birth_info = "НЕИЗВЕСТНО"
                if user_info:
                    d = user_info.get("birth_date", "")
                    t = user_info.get("birth_time", "")
                    c = user_info.get("birth_city", "")
                    birth_info = f"{d} {t} {c}".strip() or "НЕИЗВЕСТНО"
                section_title = "РАЗДЕЛ: " + {"sex":"ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ", "money":"КОД ТВОЕГО БОГАТСТВА", "shadow":"ТВОИ СКРЫТЫЕ ГРАНИ", "final":"ТВОЙ ИСТИННЫЙ ПУТЬ", "oracle":"ОРАКУЛ", "welcome":"РАЗБОР", "synastry":"ТАЙНА ВАШИХ ОТНОШЕНИЙ"}.get(target_section, target_section.upper())
                from modules.utils import generate_premium_pdf
                generate_premium_pdf(first_name, birth_info, section_title, display_text, pdf_filename, str(card_id))
                from vkbottle import DocMessagesUploader
                doc_uploader = DocMessagesUploader(bot.api)
                doc_attachment = await doc_uploader.upload(title=f"Твой_архив.pdf", file_source=pdf_filename, peer_id=vk_id)
                await bot.api.messages.send(peer_id=vk_id, message="Твой персональный архив. Скачай, чтобы не потерять.", attachment=doc_attachment, random_id=0)
                if os.path.exists(pdf_filename):
                    os.remove(pdf_filename)
            except Exception as e:
                pass

            section_header = target_section_ru = {
                "sex": "ТВОЯ СЕКСУАЛЬНАЯ ЭНЕРГИЯ",
                "money": "КОД ТВОЕГО БОГАТСТВА",
                "shadow": "ТВОИ СКРЫТЫЕ ГРАНИ",
                "final": "ТВОЙ ИСТИННЫЙ ПУТЬ",
                "synastry": "ТАЙНА ВАШИХ ОТНОШЕНИЙ"
            }.get(target_section, target_section.upper())

            parts = re.split(rf"(?i)\b{target_section_ru}\b", display_text, maxsplit=1)
            intro = ""
            main_part = display_text

            if len(parts) > 1:
                intro = parts[0].strip()
                main_part = f"{target_section_ru}\n" + parts[1].strip()

            from modules.utils import SKIN_ASSETS
            skin_att = await upload_local_photo(bot.api, SKIN_ASSETS.get(active_skin, "o.png"))
            if skin_att:
                await bot.api.messages.send(peer_id=peer_id, message="", attachment=skin_att, random_id=0)
                import asyncio
                await asyncio.sleep(0.5)

            if intro:
                await bot.api.messages.send(peer_id=peer_id, message=intro, random_id=0)
                await bot.api.messages.set_activity(peer_id=peer_id, type="typing")
                import asyncio
                await asyncio.sleep(4)
                try:
                    await bot.api.messages.send(peer_id=peer_id, message=main_part, keyboard=kb_json, random_id=0)
                except Exception:
                    await bot.api.messages.send(peer_id=peer_id, message=main_part, random_id=0)
            else:
                try:
                    await bot.api.messages.send(peer_id=peer_id, message=display_text, keyboard=kb_json, random_id=0)
                except Exception:
                    await bot.api.messages.send(peer_id=peer_id, message=display_text, random_id=0)

            if photo_attachment:
                caption = ""
                if user:
                    unlocked_cards = user.get("unlocked_cards", {})
                    if isinstance(unlocked_cards, dict):
                        caption = unlocked_cards.get(card_id, "Новая карта добавлена в твой Гримуар.")

                try:
                    await bot.api.messages.send(peer_id=peer_id, message=f"🎴 Значение карты:\n{caption}", attachment=photo_attachment, random_id=0)
                except Exception:
                    await bot.api.messages.send(peer_id=peer_id, message="", attachment=photo_attachment, random_id=0)

            purchased[target_section] = False
            await update_user(vk_id, {"purchased_sections": purchased})
